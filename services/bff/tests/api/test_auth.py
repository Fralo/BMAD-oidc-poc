"""End-to-end route tests for `/auth/login` and `/auth/callback` (Story 1.5).

Uses the synthetic IdP fixture to drive token exchange + id-token verification
without touching a real Keycloak. Exercises the AC9 scenario matrix: happy
path, all callback failure modes, cookie attributes, return_to validation.
"""

import base64
import logging
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from bff.api.auth import BFF_AUTH_STATE_COOKIE_NAME
from bff.auth.keycloak_cookie_session import sign_state_id, state_id_serializer
from bff.auth.pkce import compute_code_challenge
from bff.core.config import settings
from bff.models import entities
from bff.services.session_service import SessionService
from tests.auth.synthetic_idp import (
    DEFAULT_AUDIENCE,
    DEFAULT_ISSUER,
    DEFAULT_JWKS_URL,
    DEFAULT_TOKEN_URL,
    SyntheticIdp,
    build_synthetic_idp,
    stash_authorization_code,
)

# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------


@pytest.fixture
def configured_idp(monkeypatch: pytest.MonkeyPatch):
    """Spin up the synthetic IdP AND point the BFF's settings at it.

    Yields (respx_router, SyntheticIdp).
    """
    monkeypatch.setattr(settings, "oidc_issuer_url", DEFAULT_ISSUER)
    monkeypatch.setattr(settings, "oidc_jwks_url", DEFAULT_JWKS_URL)
    monkeypatch.setattr(settings, "oidc_authorize_url_browser", DEFAULT_ISSUER)
    monkeypatch.setattr(settings, "oidc_client_id", DEFAULT_AUDIENCE)
    monkeypatch.setattr(settings, "bff_client_secret", "test-bff-secret")
    monkeypatch.setattr(settings, "bff_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings, "bff_session_cookie_name", "bff_session")
    monkeypatch.setattr(settings, "bff_csrf_cookie_name", "bff_csrf")
    monkeypatch.setattr(settings, "bff_session_cookie_secure", False)

    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        yield mock, idp


async def _authorize_and_capture(
    client: AsyncClient, *, return_to: str | None = "/books"
) -> tuple[dict[str, str], str]:
    """Call /auth/login, return parsed query params + the state-id cookie value.

    `client` MUST be the no-redirects client so the 302 is inspectable.
    """
    path = "/auth/login"
    if return_to is not None:
        path = f"/auth/login?return_to={return_to}"
    response = await client.get(path)
    assert response.status_code == 302, response.text
    parsed = urlparse(response.headers["Location"])
    params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    state_cookie = response.cookies.get(BFF_AUTH_STATE_COOKIE_NAME)
    assert state_cookie, "state-id cookie missing"
    return params, state_cookie


async def _complete_login(
    client: AsyncClient,
    session: AsyncSession,
    idp: SyntheticIdp,
    *,
    return_to: str | None = "/books",
    nonce_override: str | None = None,
    sub: str = "test-sub-001",
):
    """Run /auth/login then /auth/callback, returning the final response."""
    params, state_cookie = await _authorize_and_capture(client, return_to=return_to)
    state_value = params["state"]
    challenge = params["code_challenge"]

    # Fetch the auth_state row to grab its `code_verifier` for the IdP stash.
    row = (
        (
            await session.execute(
                select(entities.AuthState).where(
                    entities.AuthState.state == state_value
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert compute_code_challenge(row.code_verifier) == challenge

    # Stash the authorization code with the nonce/sub the id_token will carry.
    nonce_for_token = nonce_override if nonce_override is not None else row.nonce
    code = stash_authorization_code(
        idp,
        code_verifier=row.code_verifier,
        nonce=nonce_for_token,
        sub=sub,
    )
    response = await client.get(
        f"/auth/callback?code={code}&state={state_value}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: state_cookie},
    )
    return response


# ---------------------------------------------------------------------------
# /auth/login
# ---------------------------------------------------------------------------


async def test_auth_login_redirects_to_idp_with_pkce_params(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    params, _ = await _authorize_and_capture(client_no_redirects, return_to="/books")
    assert params["client_id"] == DEFAULT_AUDIENCE
    assert params["response_type"] == "code"
    assert params["code_challenge_method"] == "S256"
    assert params["code_challenge"]
    assert params["state"]
    assert params["nonce"]
    assert "openid" in params["scope"]
    assert "offline_access" in params["scope"]
    assert "reading-speed:read" in params["scope"]
    assert "reading-speed:write" in params["scope"]
    # Row persisted with the right return_to.
    result = await session.execute(
        select(entities.AuthState).where(entities.AuthState.state == params["state"])
    )
    row = result.scalars().first()
    assert row is not None
    assert row.return_to == "/books"


async def test_auth_login_state_cookie_attributes(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    response = await client_no_redirects.get("/auth/login?return_to=/books")
    set_cookie = response.headers.get("set-cookie", "")
    assert "bff_auth_state=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie or "SameSite=Lax" in set_cookie
    assert "Max-Age=300" in set_cookie
    assert "Path=/" in set_cookie


async def test_auth_login_secure_flag_follows_setting(
    client_no_redirects: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    configured_idp,
) -> None:
    monkeypatch.setattr(settings, "bff_session_cookie_secure", True)
    response = await client_no_redirects.get("/auth/login?return_to=/books")
    set_cookie = response.headers.get("set-cookie", "")
    assert "Secure" in set_cookie


@pytest.mark.parametrize(
    ("input_return", "expected_normalized"),
    [
        ("/books", "/books"),
        ("/", "/"),
        ("/foo?bar=baz", "/foo?bar=baz"),
        ("//evil.example", "/"),
        ("https://evil.example", "/"),
        ("javascript:alert(1)", "/"),
        ("", "/"),
        ("/" + "a" * 2000, "/"),
        (None, "/"),
    ],
)
async def test_auth_login_normalizes_return_to(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
    input_return: str | None,
    expected_normalized: str,
) -> None:
    params, _ = await _authorize_and_capture(
        client_no_redirects, return_to=input_return
    )
    row = (
        (
            await session.execute(
                select(entities.AuthState).where(
                    entities.AuthState.state == params["state"]
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    assert row.return_to == expected_normalized


# ---------------------------------------------------------------------------
# /auth/callback — happy path
# ---------------------------------------------------------------------------


async def test_auth_callback_happy_path_sets_cookies_and_redirects(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    _, idp = configured_idp
    response = await _complete_login(
        client_no_redirects, session, idp, return_to="/books"
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/books"

    cookies = response.headers.get_list("set-cookie")
    assert any("bff_session=" in c for c in cookies)
    assert any("bff_csrf=" in c for c in cookies)
    # State-id cookie cleared (Max-Age=0).
    cleared = [c for c in cookies if "bff_auth_state=" in c]
    assert cleared
    assert any("Max-Age=0" in c for c in cleared)

    # bff_session is HttpOnly, bff_csrf is NOT (architecture A5).
    session_cookie = next(c for c in cookies if c.startswith("bff_session="))
    csrf_cookie = next(c for c in cookies if c.startswith("bff_csrf="))
    assert "HttpOnly" in session_cookie
    assert "HttpOnly" not in csrf_cookie

    # AC9 row 29: bff_session_cookie_secure=False → neither cookie carries Secure.
    assert "Secure" not in session_cookie
    assert "Secure" not in csrf_cookie

    # Sessions row was persisted.
    result = await session.execute(select(entities.Session))
    sessions = result.scalars().all()
    assert len(sessions) == 1
    assert sessions[0].sub == "test-sub-001"


async def test_auth_callback_unsafe_return_to_redirects_to_root(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    _, idp = configured_idp
    response = await _complete_login(
        client_no_redirects, session, idp, return_to="https://evil.example"
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


async def test_auth_callback_deletes_auth_state_row(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    _, idp = configured_idp
    await _complete_login(client_no_redirects, session, idp)
    result = await session.execute(select(entities.AuthState))
    assert result.scalars().all() == []


# ---------------------------------------------------------------------------
# /auth/callback — failure modes
# ---------------------------------------------------------------------------


async def test_auth_callback_missing_state_returns_400(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    response = await client_no_redirects.get("/auth/callback?code=abc")
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_missing_state_cookie_returns_400(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    response = await client_no_redirects.get("/auth/callback?code=abc&state=something")
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_tampered_state_cookie_returns_400(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    response = await client_no_redirects.get(
        "/auth/callback?code=abc&state=something",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: "not.a.signed.value"},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_state_row_missing_returns_400(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    # Sign a state-id cookie for a never-existing row id.
    serializer = state_id_serializer(settings.bff_client_secret)
    signed = sign_state_id(serializer, "ghost-row-id")
    response = await client_no_redirects.get(
        "/auth/callback?code=abc&state=ghost-state",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: signed},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_cookie_row_id_mismatch_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """Cookie points at row A but the `state` matches a different row B's state."""
    params, _ = await _authorize_and_capture(client_no_redirects, return_to="/books")
    # Sign a state-id cookie for a different (fictional) row.
    serializer = state_id_serializer(settings.bff_client_secret)
    forged = sign_state_id(serializer, "row-id-that-does-not-match")
    response = await client_no_redirects.get(
        f"/auth/callback?code=abc&state={params['state']}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: forged},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"
    # The legitimate row was consumed (defense in depth) so a replay would fail too.
    result = await session.execute(select(entities.AuthState))
    assert result.scalars().all() == []


async def test_auth_callback_pkce_mismatch_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """The IdP rejects the code+verifier exchange."""
    _, idp = configured_idp
    params, state_cookie = await _authorize_and_capture(
        client_no_redirects, return_to="/books"
    )

    row = (
        (
            await session.execute(
                select(entities.AuthState).where(
                    entities.AuthState.state == params["state"]
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    # Stash a code with a DIFFERENT verifier — exchange will 400 at IdP.
    code = stash_authorization_code(idp, code_verifier="wrong-verifier")
    response = await client_no_redirects.get(
        f"/auth/callback?code={code}&state={params['state']}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: state_cookie},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_id_token_nonce_mismatch_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """IdP issues an id_token with a different nonce than the auth_state."""
    _, idp = configured_idp
    response = await _complete_login(
        client_no_redirects,
        session,
        idp,
        nonce_override="completely-different-nonce",
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_missing_code_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    params, state_cookie = await _authorize_and_capture(
        client_no_redirects, return_to="/books"
    )
    response = await client_no_redirects.get(
        f"/auth/callback?state={params['state']}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: state_cookie},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_expired_auth_state_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """An expired row is silently deleted; the callback gets a 400."""
    serializer = state_id_serializer(settings.bff_client_secret)
    expired = entities.AuthState(
        id="expired-id-xyz",
        code_verifier="v",
        state="expired-state-xyz",
        nonce="n",
        return_to="/",
        expires_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    session.add(expired)
    await session.commit()
    signed = sign_state_id(serializer, "expired-id-xyz")
    response = await client_no_redirects.get(
        "/auth/callback?code=abc&state=expired-state-xyz",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: signed},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"

    # Row was deleted by consume_auth_state's expired-row path.
    leftover = await SessionService().consume_auth_state(
        session, state="expired-state-xyz"
    )
    assert leftover is None


async def test_auth_callback_failure_clears_state_cookie(
    client_no_redirects: AsyncClient,
    configured_idp,
) -> None:
    response = await client_no_redirects.get(
        "/auth/callback?code=x"  # missing state → 400
    )
    set_cookie = response.headers.get("set-cookie", "")
    assert "bff_auth_state=" in set_cookie
    assert "Max-Age=0" in set_cookie


# ---------------------------------------------------------------------------
# /auth/login → /auth/callback round-trip — return_to fallback (AC9 row 15)
# ---------------------------------------------------------------------------


async def test_auth_callback_no_return_to_redirects_to_root(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """AC9 row 15: no return_to → auth_state row gets '/', callback 302s to '/'."""
    _, idp = configured_idp
    response = await _complete_login(client_no_redirects, session, idp, return_to=None)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


# ---------------------------------------------------------------------------
# id_token claim-mismatch end-to-end tests (AC9 rows 10, 11, 13)
# ---------------------------------------------------------------------------


async def _login_with_id_token_override(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    idp,
    *,
    make_token,  # callable(nonce: str) -> str
) -> Response:
    """Run /auth/login then /auth/callback injecting a custom id_token."""
    params, state_cookie = await _authorize_and_capture(client_no_redirects)
    row = (
        (
            await session.execute(
                select(entities.AuthState).where(
                    entities.AuthState.state == params["state"]
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    bad_token = make_token(row.nonce)
    code = stash_authorization_code(
        idp,
        code_verifier=row.code_verifier,
        nonce=row.nonce,
        id_token_override=bad_token,
    )
    return await client_no_redirects.get(
        f"/auth/callback?code={code}&state={params['state']}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: state_cookie},
    )


async def test_auth_callback_id_token_aud_mismatch_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """AC9 row 10: id_token aud mismatch → 400 auth_state_invalid."""
    _, idp = configured_idp
    response = await _login_with_id_token_override(
        client_no_redirects,
        session,
        idp,
        make_token=lambda nonce: idp.make_id_token(audience="wrong-aud", nonce=nonce),
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_id_token_iss_mismatch_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """AC9 row 11: id_token iss mismatch → 400 auth_state_invalid."""
    _, idp = configured_idp
    response = await _login_with_id_token_override(
        client_no_redirects,
        session,
        idp,
        make_token=lambda nonce: idp.make_id_token(
            issuer="http://attacker.example", nonce=nonce
        ),
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


async def test_auth_callback_id_token_expired_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
) -> None:
    """AC9 row 13: id_token exp in the past → 400 auth_state_invalid."""
    _, idp = configured_idp
    response = await _login_with_id_token_override(
        client_no_redirects,
        session,
        idp,
        make_token=lambda nonce: idp.make_id_token(
            exp_offset_seconds=-300, nonce=nonce
        ),
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


# ---------------------------------------------------------------------------
# JWKS-fetch failure at callback time (AC9 row 14)
# ---------------------------------------------------------------------------


async def test_auth_callback_jwks_fetch_failure_returns_400(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    configured_idp,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC9 row 14: JWKS endpoint unreachable → 400 auth_state_invalid."""
    import bff.auth.keycloak_cookie_session as _kcs

    _, idp = configured_idp
    params, state_cookie = await _authorize_and_capture(client_no_redirects)
    row = (
        (
            await session.execute(
                select(entities.AuthState).where(
                    entities.AuthState.state == params["state"]
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None
    code = stash_authorization_code(
        idp, code_verifier=row.code_verifier, nonce=row.nonce
    )

    # Clear the JWKS key cache so fetch_data is called for this request.
    monkeypatch.setattr(_kcs, "_jwks_clients", {})

    def _raise_jwks_error(self: jwt.PyJWKClient) -> None:
        raise jwt.PyJWKClientError("JWKS endpoint unreachable for test")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _raise_jwks_error)

    response = await client_no_redirects.get(
        f"/auth/callback?code={code}&state={params['state']}",
        cookies={BFF_AUTH_STATE_COOKIE_NAME: state_cookie},
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "auth_state_invalid"


# ===========================================================================
# /auth/logout (Story 1.7)
# ===========================================================================


@pytest.fixture
def logout_setup(monkeypatch: pytest.MonkeyPatch, configured_idp):
    """Build on `configured_idp`, but override `bff_base_url` to match the
    test client's `base_url` so the CSRF middleware's Origin check accepts
    the request. Yields `(respx_mock, SyntheticIdp)` like `configured_idp`.
    """
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    return configured_idp


async def _seed_session(
    client: AsyncClient,
    session: AsyncSession,
    idp: SyntheticIdp,
) -> tuple[str, str, entities.Session]:
    """Run /auth/login + /auth/callback; return cookies + the persisted row."""
    response = await _complete_login(client, session, idp)
    assert response.status_code == 302
    session_cookie = response.cookies.get(settings.bff_session_cookie_name)
    csrf_value = response.cookies.get(settings.bff_csrf_cookie_name)
    assert session_cookie, "bff_session cookie was not issued on login"
    assert csrf_value, "bff_csrf cookie was not issued on login"

    rows = (await session.execute(select(entities.Session))).scalars().all()
    assert len(rows) == 1, "exactly one sessions row should exist after login"
    return session_cookie, csrf_value, rows[0]


async def _logout(
    client: AsyncClient,
    *,
    session_cookie: str | None,
    csrf_value: str | None,
    csrf_header: str | None = "__from_cookie__",
    origin: str = "http://test",
) -> Response:
    """POST /auth/logout with cookies + CSRF header + Origin.

    `csrf_header="__from_cookie__"` (default) mirrors the cookie value (happy
    path / honest client). Pass an explicit value (or `None` to omit) to
    exercise the CSRF middleware's reject path.
    """
    cookies: dict[str, str] = {}
    if session_cookie is not None:
        cookies[settings.bff_session_cookie_name] = session_cookie
    if csrf_value is not None:
        cookies[settings.bff_csrf_cookie_name] = csrf_value

    headers: dict[str, str] = {"Origin": origin}
    header_value: str | None = (
        csrf_value if csrf_header == "__from_cookie__" else csrf_header
    )
    if header_value is not None:
        headers["X-CSRF-Token"] = header_value

    return await client.post("/auth/logout", cookies=cookies, headers=headers)


def _parse_set_cookies(response: Response, name: str) -> list[SimpleCookie]:
    """Return one parsed `SimpleCookie` per `Set-Cookie` header that defines
    a cookie named `name`. We parse each header individually so multiple
    `Set-Cookie` lines for the same cookie don't collapse together.
    """
    out: list[SimpleCookie] = []
    for raw in response.headers.get_list("set-cookie"):
        jar = SimpleCookie()
        jar.load(raw)
        if name in jar:
            out.append(jar)
    return out


def _cookie_attr(set_cookie_line: str, attr: str) -> str | None:
    """Extract a Set-Cookie attribute value by exact key match.

    `"Path=/" in line` falsely matches `"Path=/api"` — splitting on `;` and
    comparing the trimmed key ensures the attribute value is exactly `/`
    (or whatever else the production code set).
    """
    for chunk in set_cookie_line.split(";"):
        key, _, value = chunk.strip().partition("=")
        if key.lower() == attr.lower():
            return value
    return None


# ---------------------------------------------------------------------------
# Scenario 1: happy path
# ---------------------------------------------------------------------------


async def test_logout_happy_path_returns_204_and_clears_session(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, row = await _seed_session(
        client_no_redirects, session, idp
    )
    stored_id_token = row.id_token

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    # 204 with empty body (AC2 + AC8 scenario 13). Per RFC 7230 §3.3.2 a 204
    # response MUST NOT carry a content-length header; FastAPI omits it
    # correctly, so we only assert the body is empty.
    assert response.status_code == 204
    assert response.content == b""
    assert "content-length" not in response.headers

    # Revocation captured with correct form fields (AC8 scenario 1).
    assert len(idp.captured_revocations) == 1
    rev = idp.captured_revocations[0]
    assert rev["token"] == "synthetic-refresh-token"
    assert rev["token_type_hint"] == "refresh_token"

    # End-session captured with the stored id_token (AC8 scenario 1).
    assert len(idp.captured_end_sessions) == 1
    es = idp.captured_end_sessions[0]
    assert es["id_token_hint"] == stored_id_token
    assert es["client_id"] == DEFAULT_AUDIENCE
    assert es["client_secret"] == "test-bff-secret"

    # The sessions row was deleted.
    result = await session.execute(select(entities.Session))
    assert result.scalars().all() == []

    # Both clearing cookies carry Max-Age=0.
    session_cookies = _parse_set_cookies(response, settings.bff_session_cookie_name)
    csrf_cookies = _parse_set_cookies(response, settings.bff_csrf_cookie_name)
    assert session_cookies and csrf_cookies
    assert session_cookies[0][settings.bff_session_cookie_name]["max-age"] == "0"
    assert csrf_cookies[0][settings.bff_csrf_cookie_name]["max-age"] == "0"


# ---------------------------------------------------------------------------
# Scenario 14: HTTP Basic auth on /revocation (RFC 7009 §2.1)
# ---------------------------------------------------------------------------


async def test_logout_uses_http_basic_auth_on_revocation(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    auth_header = idp.captured_revocations[0]["_authorization"]
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[len("Basic ") :]).decode("ascii")
    assert decoded == f"{DEFAULT_AUDIENCE}:test-bff-secret"


# ---------------------------------------------------------------------------
# Scenario 2: revocation 5xx → 204; end-session still called
# ---------------------------------------------------------------------------


async def test_logout_revocation_5xx_still_returns_204(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    idp.revocation_response_override = httpx.Response(500)
    caplog.set_level(logging.WARNING, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert response.status_code == 204
    # Both upstream calls happened — revocation 500'd (caught) and end-session
    # still ran per A7. Without explicitly asserting captured_revocations, a
    # regression that no-ops the revoke call would slip through silently.
    assert len(idp.captured_revocations) == 1
    assert len(idp.captured_end_sessions) == 1
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    assert any(
        "auth_logout_revocation_failed" in rec.message
        and "HTTPStatusError" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Scenarios 3/4: revocation ConnectError / ReadTimeout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "classifier"),
    [
        (httpx.ConnectError("refused"), "ConnectError"),
        (httpx.ReadTimeout("slow"), "ReadTimeout"),
        (httpx.ConnectTimeout("dns hang"), "ConnectTimeout"),
    ],
)
async def test_logout_revocation_transport_failure_still_returns_204(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
    override: httpx.HTTPError,
    classifier: str,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    idp.revocation_response_override = override
    caplog.set_level(logging.WARNING, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert response.status_code == 204
    # Revocation transport call DID happen (it threw before reaching the AS,
    # but the BFF still attempted it — captured by the synthetic IdP's
    # handler-raise path before the request_content was even parsed).
    assert len(idp.captured_revocations) == 1
    assert len(idp.captured_end_sessions) == 1
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    assert any(
        f"auth_logout_revocation_failed: {classifier}" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Scenarios 5/6: end-session 5xx / ConnectError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "classifier"),
    [
        (httpx.Response(500), "HTTPStatusError"),
        (httpx.ConnectError("refused"), "ConnectError"),
    ],
)
async def test_logout_end_session_failure_still_returns_204(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
    override,
    classifier: str,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    idp.end_session_response_override = override
    caplog.set_level(logging.WARNING, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert response.status_code == 204
    # Revocation still happened normally.
    assert len(idp.captured_revocations) == 1
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    assert any(
        f"auth_logout_end_session_failed: {classifier}" in rec.message
        for rec in caplog.records
    )


# ---------------------------------------------------------------------------
# Scenario 7: both revocation AND end-session fail
# ---------------------------------------------------------------------------


async def test_logout_both_upstream_failures_still_returns_204(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    idp.revocation_response_override = httpx.Response(502)
    idp.end_session_response_override = httpx.ConnectError("down")
    caplog.set_level(logging.WARNING, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert response.status_code == 204
    # Both upstream calls were attempted before being short-circuited by
    # their respective overrides; assert the captures so a regression that
    # silently skips either call is detected.
    assert len(idp.captured_revocations) == 1
    assert len(idp.captured_end_sessions) == 1
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    messages = [rec.message for rec in caplog.records]
    assert any("auth_logout_revocation_failed" in m for m in messages)
    assert any("auth_logout_end_session_failed" in m for m in messages)


# ---------------------------------------------------------------------------
# Scenario 8: missing session cookie → 401 session_expired
# ---------------------------------------------------------------------------


async def test_logout_missing_session_cookie_returns_401(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    # Send a CSRF cookie+header so the CSRF middleware lets the request through;
    # the handler then sees a missing session cookie and emits the 401 envelope.
    response = await _logout(
        client_no_redirects,
        session_cookie=None,
        csrf_value="csrf-without-session",
    )

    assert response.status_code == 401
    body = response.json()
    assert body["errorCode"] == "session_expired"
    # No IdP calls.
    assert idp.captured_revocations == []
    assert idp.captured_end_sessions == []
    # Defensive cookie clears emitted.
    session_clears = _parse_set_cookies(response, settings.bff_session_cookie_name)
    csrf_clears = _parse_set_cookies(response, settings.bff_csrf_cookie_name)
    assert session_clears and csrf_clears
    assert session_clears[0][settings.bff_session_cookie_name]["max-age"] == "0"
    assert csrf_clears[0][settings.bff_csrf_cookie_name]["max-age"] == "0"


# ---------------------------------------------------------------------------
# Scenario 9: unknown session cookie → 401 session_expired
# ---------------------------------------------------------------------------


async def test_logout_unknown_session_cookie_returns_401(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    response = await _logout(
        client_no_redirects,
        session_cookie="does-not-exist",
        csrf_value="csrf-irrelevant",
    )

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    assert idp.captured_revocations == []
    assert idp.captured_end_sessions == []


# ---------------------------------------------------------------------------
# Scenario 10: expired session row → 401, row deleted lazily
# ---------------------------------------------------------------------------


async def test_logout_expired_session_returns_401_and_deletes_row(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    # Seed a directly-inserted expired session row.
    expired = entities.Session(
        id="expired-session-id",
        sub="sub-expired",
        access_token="a",
        refresh_token="r",
        id_token="i",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
        csrf_secret="csrf-expired",
    )
    session.add(expired)
    await session.commit()

    response = await _logout(
        client_no_redirects,
        session_cookie="expired-session-id",
        csrf_value="csrf-irrelevant",
    )

    assert response.status_code == 401
    assert response.json()["errorCode"] == "session_expired"
    # No IdP calls; row was cleaned up lazily.
    assert idp.captured_revocations == []
    assert idp.captured_end_sessions == []
    result = await session.execute(
        select(entities.Session).where(entities.Session.id == "expired-session-id")
    )
    assert result.scalars().first() is None


# ---------------------------------------------------------------------------
# Scenario 11: refresh-replay rejection after revocation (AC7)
# ---------------------------------------------------------------------------


async def test_logout_revokes_refresh_token_at_idp(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    mock, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    assert idp.revoked_refresh_tokens == set()

    await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert "synthetic-refresh-token" in idp.revoked_refresh_tokens

    # Now replay the revoked refresh_token at the IdP's /token endpoint;
    # the synthetic IdP must return 400 invalid_grant.
    async with httpx.AsyncClient() as raw:
        replay = await raw.post(
            DEFAULT_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": "synthetic-refresh-token",
                "client_id": DEFAULT_AUDIENCE,
                "client_secret": "test-bff-secret",
            },
        )
    assert replay.status_code == 400
    assert replay.json() == {"error": "invalid_grant"}
    _ = mock  # mock context kept alive by the fixture; lint sees it as unused.


# ---------------------------------------------------------------------------
# Scenario 12: cookie attributes on clear (HttpOnly / SameSite / Path / Secure)
# ---------------------------------------------------------------------------


async def test_logout_clear_cookies_have_correct_attributes(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    raw_lines = response.headers.get_list("set-cookie")
    session_prefix = f"{settings.bff_session_cookie_name}="
    csrf_prefix = f"{settings.bff_csrf_cookie_name}="
    session_line = next(line for line in raw_lines if line.startswith(session_prefix))
    csrf_line = next(line for line in raw_lines if line.startswith(csrf_prefix))

    # Session cookie clear: HttpOnly + SameSite=lax + Path=/ + Max-Age=0.
    assert "HttpOnly" in session_line
    assert "SameSite=lax" in session_line or "SameSite=Lax" in session_line
    # Substring "Path=/" matches "Path=/api" too; assert the attribute
    # value is exactly "/" by walking the parsed attribute list.
    assert _cookie_attr(session_line, "Path") == "/"
    assert "Max-Age=0" in session_line

    # CSRF cookie clear: NOT HttpOnly + SameSite=lax + Path=/ + Max-Age=0.
    assert "HttpOnly" not in csrf_line
    assert "SameSite=lax" in csrf_line or "SameSite=Lax" in csrf_line
    assert _cookie_attr(csrf_line, "Path") == "/"
    assert "Max-Age=0" in csrf_line

    # bff_session_cookie_secure=False (logout_setup default) → no Secure flag.
    assert "Secure" not in session_line
    assert "Secure" not in csrf_line


async def test_logout_clear_cookies_carry_secure_when_setting_enabled(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, idp = logout_setup
    monkeypatch.setattr(settings, "bff_session_cookie_secure", True)
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    raw_lines = response.headers.get_list("set-cookie")
    cleared_session = [
        line
        for line in raw_lines
        if line.startswith(f"{settings.bff_session_cookie_name}=")
        and "Max-Age=0" in line
    ]
    cleared_csrf = [
        line
        for line in raw_lines
        if line.startswith(f"{settings.bff_csrf_cookie_name}=") and "Max-Age=0" in line
    ]
    assert cleared_session and "Secure" in cleared_session[0]
    assert cleared_csrf and "Secure" in cleared_csrf[0]


# ---------------------------------------------------------------------------
# Scenario 15: missing CSRF → 403 csrf_invalid (Story 1.6 middleware)
# ---------------------------------------------------------------------------


async def test_logout_missing_csrf_header_returns_403(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
        csrf_header=None,  # omit X-CSRF-Token entirely
    )

    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"
    # Handler was never reached, so no IdP traffic and the row is intact.
    assert idp.captured_revocations == []
    assert idp.captured_end_sessions == []
    rows = (await session.execute(select(entities.Session))).scalars().all()
    assert len(rows) == 1


async def test_logout_mismatched_csrf_header_returns_403(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
        csrf_header="not-the-real-secret",
    )
    assert response.status_code == 403
    assert response.json()["errorCode"] == "csrf_invalid"
    _ = idp


# ---------------------------------------------------------------------------
# Empty-token guards (post-review P4): skip upstream calls when the stored
# token is empty so the WARN log doesn't fabricate phantom "AS failures".
# ---------------------------------------------------------------------------


async def _insert_logout_row(
    session: AsyncSession,
    *,
    session_id: str = "row-with-empty-tokens",
    refresh_token: str = "",
    id_token: str = "",
) -> str:
    row = entities.Session(
        id=session_id,
        sub="sub-empty-tokens",
        access_token="a",
        refresh_token=refresh_token,
        id_token=id_token,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        csrf_secret="csrf-empty",
    )
    session.add(row)
    await session.commit()
    return session_id


async def test_logout_empty_refresh_token_skips_revoke(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, idp = logout_setup
    session_id = await _insert_logout_row(
        session, refresh_token="", id_token="some-id-token"
    )
    caplog.set_level(logging.INFO, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_id,
        csrf_value="csrf-empty",
    )

    assert response.status_code == 204
    # No revocation request fired — the BFF didn't try to revoke ``.
    assert idp.captured_revocations == []
    # End-session still runs because id_token IS present.
    assert len(idp.captured_end_sessions) == 1
    # Row deleted, classifier log emitted.
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    assert any("auth_logout_no_refresh_token" in r.message for r in caplog.records)


async def test_logout_empty_id_token_skips_end_session(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, idp = logout_setup
    session_id = await _insert_logout_row(
        session, refresh_token="some-refresh-token", id_token=""
    )
    caplog.set_level(logging.INFO, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_id,
        csrf_value="csrf-empty",
    )

    assert response.status_code == 204
    # Revocation DID fire (refresh_token was present).
    assert len(idp.captured_revocations) == 1
    # End-session SKIPPED — no captured request.
    assert idp.captured_end_sessions == []
    assert (await session.execute(select(entities.Session))).scalars().all() == []
    assert any("auth_logout_no_id_token" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# DB-failure guard (post-review P2): a SQLAlchemyError raised by
# `delete_session` after upstream success must NOT crash the handler — the
# cookies still clear and the response is still 204, honoring UX §J5.
# ---------------------------------------------------------------------------


async def test_logout_db_delete_failure_still_returns_204_and_clears_cookies(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.exc import OperationalError

    from bff.api import auth as auth_module

    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    caplog.set_level(logging.ERROR, logger="bff.api.auth")

    async def _boom(*args, **kwargs):
        raise OperationalError("statement", {}, Exception("db connection lost"))

    monkeypatch.setattr(auth_module._session_service, "delete_session", _boom)

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    # UX §J5: a half-logged-out state is forbidden. Even though the DB
    # delete failed, the user receives 204 with cookie-clear headers — the
    # browser-side session ends, and operations sees the failure in logs.
    assert response.status_code == 204
    raw_set_cookies = response.headers.get_list("set-cookie")
    assert any(
        line.startswith(f"{settings.bff_session_cookie_name}=") and "Max-Age=0" in line
        for line in raw_set_cookies
    )
    assert any("auth_logout_session_delete_failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Status-code classifier (post-review P6): HTTPStatusError WARN log carries
# the response status code so 401 / 429 / 5xx are distinguishable from each
# other in operations.
# ---------------------------------------------------------------------------


async def test_logout_revocation_4xx_classifier_includes_status_code(
    client_no_redirects: AsyncClient,
    session: AsyncSession,
    logout_setup,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, idp = logout_setup
    session_cookie, csrf_value, _ = await _seed_session(
        client_no_redirects, session, idp
    )
    idp.revocation_response_override = httpx.Response(401)
    caplog.set_level(logging.WARNING, logger="bff.api.auth")

    response = await _logout(
        client_no_redirects,
        session_cookie=session_cookie,
        csrf_value=csrf_value,
    )

    assert response.status_code == 204
    assert any(
        "auth_logout_revocation_failed: HTTPStatusError(401)" in rec.message
        for rec in caplog.records
    )
