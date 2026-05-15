"""End-to-end route tests for `/auth/login` and `/auth/callback` (Story 1.5).

Uses the synthetic IdP fixture to drive token exchange + id-token verification
without touching a real Keycloak. Exercises the AC9 scenario matrix: happy
path, all callback failure modes, cookie attributes, return_to validation.
"""

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

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
