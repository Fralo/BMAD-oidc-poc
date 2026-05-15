"""Unit tests for `bff.auth.keycloak_cookie_session`.

Covers:
* HMAC-signed state-id cookie round-trip + tamper + expiry detection.
* `build_authorize_url` query-param assembly.
* `exchange_code` happy path AND failure paths via the synthetic IdP.
* `verify_id_token` happy path AND every failure mode (forged signature,
  wrong issuer, wrong audience, missing required claim, expired, nonce
  mismatch, JWKS unreachable).
"""

import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from bff.auth.keycloak_cookie_session import (
    OidcVerificationError,
    build_authorize_url,
    exchange_code,
    sign_state_id,
    state_id_serializer,
    verify_id_token,
    verify_state_id,
)
from tests.auth.synthetic_idp import (
    DEFAULT_AUDIENCE,
    DEFAULT_ISSUER,
    DEFAULT_JWKS_URL,
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
    url = build_authorize_url(
        authorize_url_browser="http://localhost:8080/realms/test",
        redirect_uri="http://localhost:8000/auth/callback",
        client_id="bmad-books-bff",
        scopes=["openid", "offline_access", "reading-speed:read"],
        state="state-value",
        nonce="nonce-value",
        code_challenge="challenge-value",
    )
    assert url.startswith(
        "http://localhost:8080/realms/test/protocol/openid-connect/auth?"
    )
    assert "client_id=bmad-books-bff" in url
    assert "response_type=code" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback" in url
    assert "scope=openid+offline_access+reading-speed%3Aread" in url
    assert "state=state-value" in url
    assert "nonce=nonce-value" in url
    assert "code_challenge=challenge-value" in url
    assert "code_challenge_method=S256" in url


def test_build_authorize_url_strips_trailing_slash() -> None:
    url = build_authorize_url(
        authorize_url_browser="http://localhost:8080/realms/test/",
        redirect_uri="http://localhost:8000/auth/callback",
        client_id="x",
        scopes=["openid"],
        state="s",
        nonce="n",
        code_challenge="c",
    )
    assert "//protocol/openid-connect/auth" not in url


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------


async def test_exchange_code_happy_path() -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock)
        code = stash_authorization_code(idp, code_verifier="verifier-xyz")
        token = await exchange_code(
            code=code,
            code_verifier="verifier-xyz",
            redirect_uri="http://localhost:8000/auth/callback",
            token_url=DEFAULT_TOKEN_URL,
            client_id="test-client",
            client_secret="test-secret",
        )
    assert "access_token" in token
    assert "refresh_token" in token
    assert "id_token" in token


async def test_exchange_code_pkce_mismatch_raises() -> None:
    with respx.mock(assert_all_called=False) as mock:
        idp = build_synthetic_idp(mock)
        code = stash_authorization_code(idp, code_verifier="expected-verifier")
        with pytest.raises(OidcVerificationError, match="token_exchange_failed"):
            await exchange_code(
                code=code,
                code_verifier="wrong-verifier",
                redirect_uri="http://localhost:8000/auth/callback",
                token_url=DEFAULT_TOKEN_URL,
                client_id="test-client",
                client_secret="test-secret",
            )


async def test_exchange_code_unknown_code_raises() -> None:
    with respx.mock(assert_all_called=False) as mock:
        build_synthetic_idp(mock)
        with pytest.raises(OidcVerificationError, match="token_exchange_failed"):
            await exchange_code(
                code="never-stashed",
                code_verifier="v",
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
