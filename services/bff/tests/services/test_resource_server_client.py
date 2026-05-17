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
    _MAX_REASONABLE_EXPIRES_IN_SEC,
    ResourceServerClient,
    RsSessionTerminated,
    RsUnavailable,
    _classify_transport_error,
    _is_valid_expires_in,
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


async def test_refresh_response_non_json_body_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    """Keycloak returns 200 with a non-JSON body → _RefreshFailed → 401."""
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, content=b"<html>not json</html>")
        )
        with pytest.raises(RsSessionTerminated) as exc_info:
            await client.get_reading_speed(session, row)
    assert exc_info.value.clear_cookies is True


async def test_refresh_response_non_dict_json_terminates_session(
    session: AsyncSession, rs_settings: None
) -> None:
    """Keycloak returns 200 with a JSON list → _RefreshFailed → 401."""
    row = await _seed_session(session)
    client = _build_client()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(_RS_READING_SPEED_URL).mock(return_value=httpx.Response(401))
        mock.post(_KEYCLOAK_TOKEN_URL).mock(
            return_value=httpx.Response(200, json=["unexpected"])
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


# CR3/CR4: _is_valid_expires_in edge cases.


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3600, True),
        (60.0, True),
        (1, True),
        (_MAX_REASONABLE_EXPIRES_IN_SEC, True),
        # Rejections:
        (None, False),
        ("3600", False),  # string
        (True, False),  # bool (True is technically int but rejected)
        (False, False),
        (0, False),
        (-1, False),
        (-3600.5, False),
        (_MAX_REASONABLE_EXPIRES_IN_SEC + 1, False),
        (float("inf"), False),
        (float("-inf"), False),
        (float("nan"), False),
        ([], False),  # not numeric
    ],
)
def test_is_valid_expires_in_classifications(value: object, expected: bool) -> None:
    assert _is_valid_expires_in(value) is expected


# CR3: missing expires_in in refresh response → _RefreshFailed("malformed_response")
# (the original code silently left expires_at stale, immediately invalidating
# the just-refreshed session on the next request).


@pytest.fixture(name="rsc")
def _rsc_fixture() -> ResourceServerClient:
    return ResourceServerClient(settings, session_service=SessionService())


def _build_session(
    *, expires_at: datetime | None = None, access_token: str = "old-at"
) -> SessionRow:
    now = datetime.now(UTC)
    return SessionRow(
        id="abcdefgh-test-session-id",
        sub="user-cr3",
        access_token=access_token,
        refresh_token="old-rt",
        id_token="id",
        expires_at=(expires_at or (now + timedelta(seconds=60))).replace(tzinfo=None),
        csrf_secret="c" * 43,
    )


@respx.mock
async def test_cr3_refresh_missing_expires_in_treated_as_malformed(
    rsc: ResourceServerClient, session: AsyncSession
) -> None:
    """Keycloak omits ``expires_in`` → treat as ``_RefreshFailed`` so the
    cookie-clearing 401 path fires explicitly instead of producing a silent
    boot-the-user-out-on-next-request.
    """
    session_row = _build_session()
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    token_url = settings.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/token"
    respx.get(rs_url).mock(return_value=httpx.Response(401, json={"error": "expired"}))
    # No ``expires_in`` key in the payload.
    respx.post(token_url).mock(
        return_value=httpx.Response(
            200,
            json={"access_token": "new-at", "refresh_token": "new-rt"},
        )
    )

    with pytest.raises(RsSessionTerminated) as exc_info:
        await rsc.get_reading_speed(session, session_row)
    assert exc_info.value.clear_cookies is True


@respx.mock
@pytest.mark.parametrize(
    # NaN is excluded — JSON does not permit it on the wire (json.dumps
    # refuses; ``_is_valid_expires_in`` rejects it defensively but the
    # path is unreachable from a real Keycloak response).
    "bad_value",
    [None, "3600", -1, 0, _MAX_REASONABLE_EXPIRES_IN_SEC + 1],
)
async def test_cr3_refresh_invalid_expires_in_treated_as_malformed(
    rsc: ResourceServerClient, session: AsyncSession, bad_value: object
) -> None:
    session_row = _build_session()
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    token_url = settings.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/token"
    respx.get(rs_url).mock(return_value=httpx.Response(401, json={"error": "expired"}))
    body: dict[str, object] = {
        "access_token": "new-at",
        "refresh_token": "new-rt",
    }
    if bad_value is not None:
        body["expires_in"] = bad_value
    respx.post(token_url).mock(return_value=httpx.Response(200, json=body))

    with pytest.raises(RsSessionTerminated) as exc_info:
        await rsc.get_reading_speed(session, session_row)
    assert exc_info.value.clear_cookies is True


# CR10: RS 2xx with non-dict body → RsUnavailable (FR-ERROR-01 honest failure)
# rather than forwarding `null` to the SPA.


@respx.mock
async def test_cr10_rs_200_with_list_body_emits_rs_unavailable(
    rsc: ResourceServerClient, session: AsyncSession
) -> None:
    session_row = _build_session(
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        access_token="fresh-at",
    )
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    # RS returns a 200 with a JSON list — contract regression.
    respx.get(rs_url).mock(return_value=httpx.Response(200, json=["unexpected"]))

    with pytest.raises(RsUnavailable) as exc_info:
        await rsc.get_reading_speed(session, session_row)
    assert exc_info.value.cause == "rs_malformed_body"
    assert exc_info.value.http_status == 200


@respx.mock
async def test_cr10_rs_200_with_scalar_body_emits_rs_unavailable(
    rsc: ResourceServerClient, session: AsyncSession
) -> None:
    session_row = _build_session(
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        access_token="fresh-at",
    )
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    respx.get(rs_url).mock(return_value=httpx.Response(200, json=42))

    with pytest.raises(RsUnavailable) as exc_info:
        await rsc.get_reading_speed(session, session_row)
    assert exc_info.value.cause == "rs_malformed_body"


@respx.mock
async def test_rs_4xx_with_unparseable_body_forwards_status_with_none_body(
    rsc: ResourceServerClient, session: AsyncSession
) -> None:
    """RS 4xx that returns invalid JSON → parsed=None, status forwarded."""
    session_row = _build_session(
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        access_token="fresh-at",
    )
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    respx.get(rs_url).mock(
        return_value=httpx.Response(412, content=b"<html>not json</html>")
    )

    status, body = await rsc.get_reading_speed(session, session_row)
    assert status == 412
    assert body is None


@respx.mock
async def test_cr10_rs_4xx_with_non_dict_body_still_forwards_status(
    rsc: ResourceServerClient, session: AsyncSession
) -> None:
    """4xx with non-dict body → forwarded with parsed=None (router emits
    JSONResponse(content=None)) — the 4xx is meaningful to the SPA even
    without a body, so we don't escalate to a 5xx-style RsUnavailable."""
    session_row = _build_session(
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        access_token="fresh-at",
    )
    session.add(session_row)
    await session.commit()

    rs_url = settings.rs_base_url.rstrip("/") + "/v1/reading-speed"
    respx.get(rs_url).mock(return_value=httpx.Response(412, json=["unexpected"]))

    status, body = await rsc.get_reading_speed(session, session_row)
    assert status == 412
    assert body is None


# Coverage helpers for less-exercised transport classifiers.


def test_classify_transport_error_branches() -> None:
    assert _classify_transport_error(httpx.ConnectTimeout("x")) == "connect_timeout"
    assert _classify_transport_error(httpx.ConnectError("x")) == "connect_error"
    assert _classify_transport_error(httpx.ReadTimeout("x")) == "read_timeout"
    assert _classify_transport_error(httpx.WriteTimeout("x")) == "write_timeout"
    assert _classify_transport_error(httpx.PoolTimeout("x")) == "pool_timeout"
    assert _classify_transport_error(httpx.NetworkError("x")) == "network_error"
    # Catch-all fallback for any other httpx.HTTPError subclass.
    assert _classify_transport_error(httpx.HTTPError("x")) == "unknown_transport"
