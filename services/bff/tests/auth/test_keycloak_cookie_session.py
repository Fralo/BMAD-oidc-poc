"""Unit tests for `bff.auth.keycloak_cookie_session`.

Covers:
* HMAC-signed state-id cookie round-trip + tamper + expiry detection.
* `build_authorize_url` query-param assembly.
* `exchange_code` happy path AND failure paths via the synthetic IdP.
* `verify_id_token` happy path AND every failure mode (forged signature,
  wrong issuer, wrong audience, missing required claim, expired, nonce
  mismatch, JWKS unreachable).
"""

import base64
import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from bff.auth.keycloak_cookie_session import (
    OidcVerificationError,
    build_authorize_url,
    end_session,
    exchange_code,
    revoke_refresh_token,
    sign_state_id,
    state_id_serializer,
    verify_id_token,
    verify_state_id,
)
from tests.auth.synthetic_idp import (
    DEFAULT_AUDIENCE,
    DEFAULT_END_SESSION_URL,
    DEFAULT_ISSUER,
    DEFAULT_JWKS_URL,
    DEFAULT_REVOCATION_URL,
    DEFAULT_TOKEN_URL,
    build_synthetic_idp,
    stash_authorization_code,
)

# ---------------------------------------------------------------------------
# state-id cookie
# ---------------------------------------------------------------------------


def test_sign_and_verify_state_id_round_trip() -> None:
    serializer = state_id_serializer("a-secret-with-entropy")
    signed = sign_state_id(serializer, "row-id-abc")
    assert isinstance(signed, str)
    assert "row-id-abc" not in signed  # opaque encoding
    assert verify_state_id(serializer, signed) == "row-id-abc"


def test_verify_state_id_returns_none_on_tamper() -> None:
    serializer = state_id_serializer("a-secret")
    signed = sign_state_id(serializer, "row-id-abc")
    tampered = signed[:-2] + ("X" if signed[-1] != "X" else "Y") + signed[-1]
    assert verify_state_id(serializer, tampered) is None


def test_verify_state_id_returns_none_on_empty_or_none() -> None:
    serializer = state_id_serializer("a-secret")
    assert verify_state_id(serializer, None) is None
    assert verify_state_id(serializer, "") is None


def test_verify_state_id_returns_none_on_expired() -> None:
    serializer = state_id_serializer("a-secret")
    signed = sign_state_id(serializer, "row-id-abc")
    # itsdangerous compares with second-precision integer arithmetic; a 2s
    # sleep against max_age=1 reliably exceeds the threshold.
    time.sleep(2.1)
    assert verify_state_id(serializer, signed, max_age_seconds=1) is None


def test_verify_state_id_returns_none_when_signed_payload_is_not_str(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serializer = state_id_serializer("a-secret")
    monkeypatch.setattr(serializer, "loads", lambda _s, max_age=None: 12345)
    assert verify_state_id(serializer, "anything") is None


def test_signed_state_id_with_different_secret_does_not_verify() -> None:
    signer = state_id_serializer("secret-A")
    verifier = state_id_serializer("secret-B")
    signed = sign_state_id(signer, "row-id-abc")
    assert verify_state_id(verifier, signed) is None


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------


def test_build_authorize_url_emits_all_required_query_params() -> None:
    # Story 7.2: `authorize_endpoint` is the full authorize URL (caller
    # rebases the host:port from `OIDC_PUBLIC_BASE_URL` + discovery's path).
    url = build_authorize_url(
        authorize_endpoint=(
            "http://localhost:8080/realms/test/protocol/openid-connect/auth"
        ),
        redirect_uri="http://localhost:8000/auth/callback",
        client_id="bmad-books-bff",
        scopes=["openid", "reading-speed:read"],
        state="state-value",
        nonce="nonce-value",
    )
    assert url.startswith(
        "http://localhost:8080/realms/test/protocol/openid-connect/auth?"
    )
    assert "client_id=bmad-books-bff" in url
    assert "response_type=code" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback" in url
    assert "scope=openid+reading-speed%3Aread" in url
    assert "state=state-value" in url
    assert "nonce=nonce-value" in url
    # PKCE removed 2026-05-21 — see architecture.md Pattern Amendments.
    assert "code_challenge" not in url
    assert "code_challenge_method" not in url


def test_build_authorize_url_appends_query_to_endpoint() -> None:
    # `authorize_endpoint` is full — no trailing-slash normalization needed
    # anymore (Story 7.2 moved that responsibility to the caller's `_rebase`).
    url = build_authorize_url(
        authorize_endpoint=(
            "http://localhost:8080/realms/test/protocol/openid-connect/auth"
        ),
        redirect_uri="http://localhost:8000/auth/callback",
        client_id="x",
        scopes=["openid"],
        state="s",
        nonce="n",
    )
    assert url.count("?") == 1
    assert "?client_id=x&" in url


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------


async def test_exchange_code_happy_path() -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock)
        code = stash_authorization_code(idp)
        token = await exchange_code(
            code=code,
            redirect_uri="http://localhost:8000/auth/callback",
            token_url=DEFAULT_TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        )
    assert "access_token" in token
    assert "refresh_token" in token
    assert "id_token" in token


async def test_exchange_code_unknown_code_raises() -> None:
    with respx.mock(assert_all_called=False) as mock:
        build_synthetic_idp(mock)
        with pytest.raises(OidcVerificationError, match="token_exchange_failed"):
            await exchange_code(
                code="never-stashed",
                redirect_uri="http://localhost:8000/auth/callback",
                token_url=DEFAULT_TOKEN_URL,
                client_id="test-client",
                client_secret="test-secret",
            )


# ---------------------------------------------------------------------------
# verify_id_token
# ---------------------------------------------------------------------------


async def test_verify_id_token_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(nonce="abc", sub="user-123")
        decoded = verify_id_token(
            id_token=token,
            jwks_url=DEFAULT_JWKS_URL,
            expected_issuer=DEFAULT_ISSUER,
            expected_audience=DEFAULT_AUDIENCE,
            expected_nonce="abc",
        )
    assert decoded["sub"] == "user-123"
    assert decoded["nonce"] == "abc"


async def test_verify_id_token_wrong_signature_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        # Forge with a different key — the JWKS only carries the real public key.
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = idp.make_id_token(nonce="abc", signing_key=wrong_key)
        with pytest.raises(OidcVerificationError, match="id_token_invalid"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="abc",
            )


async def test_verify_id_token_wrong_issuer_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(issuer="http://attacker.example", nonce="abc")
        with pytest.raises(OidcVerificationError, match="id_token_invalid"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="abc",
            )


async def test_verify_id_token_wrong_audience_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(audience="not-our-aud", nonce="abc")
        with pytest.raises(OidcVerificationError, match="id_token_invalid"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="abc",
            )


async def test_verify_id_token_expired_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(nonce="abc", exp_offset_seconds=-60)
        with pytest.raises(OidcVerificationError, match="id_token_invalid"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="abc",
            )


async def test_verify_id_token_missing_nonce_claim_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(claims_override={"nonce": None})
        with pytest.raises(OidcVerificationError, match="id_token_invalid"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="abc",
            )


async def test_verify_id_token_nonce_mismatch_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock, monkeypatch=monkeypatch)
        token = idp.make_id_token(nonce="actual-nonce")
        with pytest.raises(OidcVerificationError, match="id_token_nonce_mismatch"):
            verify_id_token(
                id_token=token,
                jwks_url=DEFAULT_JWKS_URL,
                expected_issuer=DEFAULT_ISSUER,
                expected_audience=DEFAULT_AUDIENCE,
                expected_nonce="expected-different",
            )


async def test_verify_id_token_jwks_unreachable_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Patch PyJWKClient.fetch_data to simulate a failing JWKS endpoint.
    def _explode(self, *args, **kwargs):
        raise jwt.PyJWKClientError("network down")

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _explode)
    token = "header.body.signature"  # never actually parsed
    with pytest.raises(OidcVerificationError, match="id_token_invalid"):
        verify_id_token(
            id_token=token,
            jwks_url="http://idp.test/dead",
            expected_issuer=DEFAULT_ISSUER,
            expected_audience=DEFAULT_AUDIENCE,
            expected_nonce="abc",
        )


# ---------------------------------------------------------------------------
# revoke_refresh_token (Story 1.7)
# ---------------------------------------------------------------------------


async def test_revoke_refresh_token_posts_form_body_and_basic_auth() -> None:
    """RFC 7009 §2.1: form-encoded `token` + `token_type_hint=refresh_token`,
    HTTP Basic auth carrying `client_id:client_secret`.
    """
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock)
        await revoke_refresh_token(
            refresh_token="my-refresh-token",
            revocation_url=DEFAULT_REVOCATION_URL,
            client_id="test-client",
            client_secret="test-secret",
        )

    assert len(idp.captured_revocations) == 1
    captured = idp.captured_revocations[0]
    assert captured["token"] == "my-refresh-token"
    assert captured["token_type_hint"] == "refresh_token"

    # Basic auth: header captured by the synthetic IdP under "_authorization".
    auth_header = captured["_authorization"]
    assert auth_header.startswith("Basic ")
    decoded = base64.b64decode(auth_header[len("Basic ") :]).decode("ascii")
    assert decoded == "test-client:test-secret"


async def test_revoke_refresh_token_raises_on_5xx() -> None:
    """`raise_for_status()` propagates `httpx.HTTPStatusError` on non-2xx."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_REVOCATION_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await revoke_refresh_token(
                refresh_token="x",
                revocation_url=DEFAULT_REVOCATION_URL,
                client_id="c",
                client_secret="s",
            )


async def test_revoke_refresh_token_raises_on_connect_error() -> None:
    """Transport failure (`httpx.ConnectError`) propagates to the caller."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_REVOCATION_URL).mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(httpx.ConnectError):
            await revoke_refresh_token(
                refresh_token="x",
                revocation_url=DEFAULT_REVOCATION_URL,
                client_id="c",
                client_secret="s",
            )


async def test_revoke_refresh_token_raises_on_3xx() -> None:
    """A 302 from a misconfigured AS / path-rewriting proxy must NOT be
    treated as success — the refresh token would NOT actually be revoked
    while the BFF tears down the local session, silently bypassing AC7.
    """
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_REVOCATION_URL).mock(
            return_value=httpx.Response(302, headers={"location": "/login"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await revoke_refresh_token(
                refresh_token="x",
                revocation_url=DEFAULT_REVOCATION_URL,
                client_id="c",
                client_secret="s",
            )


# ---------------------------------------------------------------------------
# end_session (Story 1.7)
# ---------------------------------------------------------------------------


async def test_end_session_posts_form_body_with_id_token_hint() -> None:
    """OIDC RP-Initiated Logout: form fields id_token_hint + client_id/secret."""
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock)
        await end_session(
            id_token="my-id-token",
            end_session_url=DEFAULT_END_SESSION_URL,
            client_id="test-client",
            client_secret="test-secret",
        )

    assert len(idp.captured_end_sessions) == 1
    captured = idp.captured_end_sessions[0]
    assert captured["id_token_hint"] == "my-id-token"
    assert captured["client_id"] == "test-client"
    assert captured["client_secret"] == "test-secret"


async def test_end_session_raises_on_5xx() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_END_SESSION_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await end_session(
                id_token="x",
                end_session_url=DEFAULT_END_SESSION_URL,
                client_id="c",
                client_secret="s",
            )


async def test_end_session_raises_on_connect_error() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_END_SESSION_URL).mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        with pytest.raises(httpx.ConnectError):
            await end_session(
                id_token="x",
                end_session_url=DEFAULT_END_SESSION_URL,
                client_id="c",
                client_secret="s",
            )


async def test_end_session_raises_on_3xx() -> None:
    """`follow_redirects=False` (httpx default for POST) means a 302 from
    the AS is returned as-is. A bare `raise_for_status()` would NOT raise
    on it, silently treating "not actually logged out at the AS" as
    success.
    """
    with respx.mock(assert_all_called=False) as mock:
        mock.post(DEFAULT_END_SESSION_URL).mock(
            return_value=httpx.Response(303, headers={"location": "/logged-out"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await end_session(
                id_token="x",
                end_session_url=DEFAULT_END_SESSION_URL,
                client_id="c",
                client_secret="s",
            )
