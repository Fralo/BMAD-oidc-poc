"""Synthetic OIDC IdP test harness for Story 1.5+.

Generates an in-process RSA-2048 keypair, exposes a JWKS payload signed by
the matching key, and mounts `respx` routes that intercept the BFF's outbound
HTTP traffic to Keycloak (`/token`, `/revocation`, `/end_session`, `/certs`,
`/.well-known/openid-configuration`). Tests instantiate this fixture instead
of standing up a real Keycloak container.

`make_id_token(claims_override=...)` is the workhorse for negative-path tests
— pass a non-default `aud`/`iss`/`exp`/`nonce` (or `_signing_key` to forge
with a different RSA key) and the BFF's `verify_id_token` will reject it.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_DEFAULT_KID = "test-key-1"

# Compose-friendly test URLs. The synthetic IdP overrides the BFF's
# `oidc_*` settings to these values inside the fixture; the BFF then issues
# outbound HTTP to them and respx intercepts.
DEFAULT_ISSUER = "http://idp.test/realms/test"
DEFAULT_JWKS_URL = "http://idp.test/realms/test/protocol/openid-connect/certs"
DEFAULT_TOKEN_URL = "http://idp.test/realms/test/protocol/openid-connect/token"
DEFAULT_AUTH_URL = "http://idp.test/realms/test/protocol/openid-connect/auth"
DEFAULT_REVOCATION_URL = "http://idp.test/realms/test/protocol/openid-connect/revoke"
DEFAULT_END_SESSION_URL = "http://idp.test/realms/test/protocol/openid-connect/logout"
DEFAULT_AUDIENCE = "test-client"
DEFAULT_CLIENT_ID = "test-client"


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _int_to_b64u(value: int) -> str:
    byte_length = (value.bit_length() + 7) // 8
    return _b64u(value.to_bytes(byte_length, "big"))


def _generate_keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _public_jwk(key: rsa.RSAPrivateKey, kid: str = _DEFAULT_KID) -> dict[str, str]:
    public_numbers = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _int_to_b64u(public_numbers.n),
        "e": _int_to_b64u(public_numbers.e),
    }


@dataclass
class SyntheticIdp:
    private_key: rsa.RSAPrivateKey
    public_jwk: dict[str, str]
    discovery_doc: dict[str, Any]
    captured_token_exchanges: list[dict[str, Any]] = field(default_factory=list)
    captured_revocations: list[dict[str, Any]] = field(default_factory=list)
    captured_end_sessions: list[dict[str, Any]] = field(default_factory=list)
    # Per-code stash of the verifier challenge expected at exchange time.
    pending_codes: dict[str, str] = field(default_factory=dict)
    # Per-code stash of the nonce + sub the token handler will mint into id_tokens.
    pending_claims: dict[str, dict[str, str]] = field(default_factory=dict)
    # Refresh tokens captured at `/revocation`; populated by `_revocation_handler`
    # and consulted by `_token_handler` to reject refresh-grant replay (Story 1.7).
    revoked_refresh_tokens: set[str] = field(default_factory=set)
    # Per-handler response overrides used by Story 1.7's logout tests to simulate
    # AS failure modes. Set to an `httpx.Response` to return that response on the
    # next call (and 200 thereafter only if `..._response_override` is reset to
    # None — i.e., the override is persistent until cleared). Set to an exception
    # instance to RAISE that exception (mimicking a transport-layer failure like
    # `httpx.ConnectError` or `httpx.ReadTimeout`).
    revocation_response_override: httpx.Response | BaseException | None = None
    end_session_response_override: httpx.Response | BaseException | None = None

    def make_id_token(
        self,
        *,
        sub: str = "test-sub-001",
        preferred_username: str = "testuser",
        nonce: str = "test-nonce",
        issuer: str = DEFAULT_ISSUER,
        audience: str = DEFAULT_AUDIENCE,
        exp_offset_seconds: int = 300,
        signing_key: rsa.RSAPrivateKey | None = None,
        kid: str = _DEFAULT_KID,
        claims_override: dict[str, Any] | None = None,
    ) -> str:
        """Sign and return an RS256 id_token.

        Use `signing_key=` with a different RSA key to forge an invalid
        signature. Use `claims_override` to drop required claims.
        """
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": issuer,
            "aud": audience,
            "sub": sub,
            "exp": now + exp_offset_seconds,
            "iat": now,
            "nonce": nonce,
            "preferred_username": preferred_username,
        }
        if claims_override:
            for key, value in claims_override.items():
                if value is None and key in claims:
                    del claims[key]
                else:
                    claims[key] = value
        key = signing_key or self.private_key
        return jwt.encode(
            claims,
            _private_pem(key),
            algorithm="RS256",
            headers={"kid": kid},
        )


def _build_discovery_doc() -> dict[str, Any]:
    return {
        "issuer": DEFAULT_ISSUER,
        "authorization_endpoint": DEFAULT_AUTH_URL,
        "token_endpoint": DEFAULT_TOKEN_URL,
        "jwks_uri": DEFAULT_JWKS_URL,
        "end_session_endpoint": DEFAULT_END_SESSION_URL,
        "revocation_endpoint": DEFAULT_REVOCATION_URL,
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": [
            "openid",
            "offline_access",
            "reading-speed:read",
            "reading-speed:write",
        ],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
    }


def build_synthetic_idp(
    mock: respx.Router,
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> SyntheticIdp:
    """Register the IdP routes against an active respx Router.

    If `monkeypatch` is provided, PyJWKClient is patched so id-token JWKS
    fetches resolve to the synthetic IdP's public key without an actual HTTP
    call (PyJWKClient uses synchronous urllib, which respx does NOT intercept).
    """
    key = _generate_keypair()
    jwk = _public_jwk(key)
    idp = SyntheticIdp(
        private_key=key,
        public_jwk=jwk,
        discovery_doc=_build_discovery_doc(),
    )
    if monkeypatch is not None:
        # Clear the module-level JWKS client cache so the new PyJWKClient created
        # in this test picks up the patched `fetch_data` instead of returning the
        # previous test's cached key (cache_keys=True persists across tests).
        from bff.auth import keycloak_cookie_session as _kcs

        monkeypatch.setattr(_kcs, "_jwks_clients", {})
        monkeypatch.setattr(
            jwt.PyJWKClient,
            "fetch_data",
            lambda self: {"keys": [idp.public_jwk]},
        )

    # Discovery + JWKS — simple JSON GET handlers.
    mock.get(f"{DEFAULT_ISSUER}/.well-known/openid-configuration").mock(
        return_value=httpx.Response(200, json=idp.discovery_doc)
    )

    mock.get(DEFAULT_JWKS_URL).mock(
        return_value=httpx.Response(200, json={"keys": [jwk]})
    )

    # Token exchange — validates PKCE verifier vs stash, returns id+access+refresh.
    # Story 1.7 adds the `refresh_token` grant branch (used by /auth/logout's
    # refresh-replay-rejection integration test) — revoked tokens get 400
    # `invalid_grant`, unknown ones get 400 `invalid_request`.
    def _token_handler(request: httpx.Request) -> httpx.Response:
        body = dict(_parse_form(request.content))
        idp.captured_token_exchanges.append(body)

        if body.get("grant_type") == "refresh_token":
            refresh_token = body.get("refresh_token")
            if refresh_token and refresh_token in idp.revoked_refresh_tokens:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(400, json={"error": "invalid_request"})

        code = body.get("code")
        verifier = body.get("code_verifier")
        if not code or not verifier:
            return httpx.Response(400, json={"error": "invalid_request"})
        expected = idp.pending_codes.pop(code, None)
        if expected is None:
            return httpx.Response(400, json={"error": "invalid_grant"})
        if expected != verifier:
            return httpx.Response(400, json={"error": "invalid_grant"})
        claims = idp.pending_claims.pop(code, {})
        id_token_override = claims.pop("_id_token", None)
        nonce = claims.get("nonce", "test-nonce")
        sub = claims.get("sub", "test-sub-001")
        id_token = id_token_override or idp.make_id_token(sub=sub, nonce=nonce)
        return httpx.Response(
            200,
            json={
                "access_token": "synthetic-access-token",
                "refresh_token": "synthetic-refresh-token",
                "id_token": id_token,
                "token_type": "Bearer",
                "expires_in": 300,
                "scope": "openid offline_access",
            },
        )

    mock.post(DEFAULT_TOKEN_URL).mock(side_effect=_token_handler)

    # Story 1.7: capture the Authorization header (Basic auth assertion in
    # test_auth.py scenario 14) AND populate `revoked_refresh_tokens` so the
    # refresh-grant rejection branch above can see them. Failure-mode tests
    # set `idp.revocation_response_override` to control the response.
    def _revocation_handler(request: httpx.Request) -> httpx.Response:
        captured = dict(_parse_form(request.content))
        captured["_authorization"] = request.headers.get("authorization", "")
        idp.captured_revocations.append(captured)

        # Record the revocation BEFORE consulting the response override.
        # Otherwise a test using `revocation_response_override = Response(200)`
        # would silently skip the bookkeeping, and a follow-up refresh-grant
        # replay against the same token would NOT be rejected.
        token = captured.get("token")
        if token:
            idp.revoked_refresh_tokens.add(token)

        override = idp.revocation_response_override
        if isinstance(override, BaseException):
            raise override
        if isinstance(override, httpx.Response):
            return override

        return httpx.Response(200)

    mock.post(DEFAULT_REVOCATION_URL).mock(side_effect=_revocation_handler)

    def _end_session_handler(request: httpx.Request) -> httpx.Response:
        idp.captured_end_sessions.append(dict(_parse_form(request.content)))

        override = idp.end_session_response_override
        if isinstance(override, BaseException):
            raise override
        if isinstance(override, httpx.Response):
            return override

        return httpx.Response(200)

    mock.post(DEFAULT_END_SESSION_URL).mock(side_effect=_end_session_handler)

    return idp


def stash_authorization_code(
    idp: SyntheticIdp,
    *,
    code_verifier: str,
    nonce: str | None = None,
    sub: str | None = None,
    code: str | None = None,
    id_token_override: str | None = None,
) -> str:
    """Pre-register a code↔verifier pair the synthetic IdP will accept at `/token`.

    `nonce` and `sub` control the id_token claims the IdP mints on success.
    `id_token_override` injects a pre-built id_token (e.g., for negative tests
    with wrong aud/iss/exp). Returns the `code` (autogenerated if not supplied).
    """
    if code is None:
        code = "code-" + uuid.uuid4().hex
    idp.pending_codes[code] = code_verifier
    claims: dict[str, str] = {}
    if nonce is not None:
        claims["nonce"] = nonce
    if sub is not None:
        claims["sub"] = sub
    if id_token_override is not None:
        claims["_id_token"] = id_token_override
    if claims:
        idp.pending_claims[code] = claims
    return code


def _parse_form(content: bytes) -> list[tuple[str, str]]:
    """Parse a `application/x-www-form-urlencoded` body into key/value pairs.

    We avoid `httpx.QueryParams` here because some `respx` request objects
    arrive with `content` set but `read()` already consumed. The body is
    always ASCII for OAuth flows.
    """
    text = content.decode("ascii", errors="replace") if content else ""
    out: list[tuple[str, str]] = []
    if not text:
        return out
    for pair in text.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        out.append((_url_decode(key), _url_decode(value)))
    return out


def _url_decode(s: str) -> str:
    from urllib.parse import unquote_plus

    return unquote_plus(s)


# Re-export for convenience.
__all__ = [
    "DEFAULT_AUDIENCE",
    "DEFAULT_AUTH_URL",
    "DEFAULT_CLIENT_ID",
    "DEFAULT_END_SESSION_URL",
    "DEFAULT_ISSUER",
    "DEFAULT_JWKS_URL",
    "DEFAULT_REVOCATION_URL",
    "DEFAULT_TOKEN_URL",
    "SyntheticIdp",
    "build_synthetic_idp",
    "stash_authorization_code",
]
