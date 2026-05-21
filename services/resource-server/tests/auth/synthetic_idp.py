"""Synthetic OIDC IdP test harness for Story 3.2 (`oidc_bearer` mode).

Generates an in-process RSA-2048 keypair, exposes a JWKS payload signed by the
matching key, and **monkeypatches** `jwt.PyJWKClient.fetch_data` so signature
verification resolves to the synthetic public JWK without an actual HTTP call.

PyJWKClient uses synchronous `urllib`, which httpx/respx mocks do NOT intercept;
the BFF's Story 1.5 surfaced this and the only reliable mock-point is
`fetch_data`. The RS harness reproduces that pattern locally — cross-service
Python imports are forbidden per architecture §"Architectural Boundaries".

Exports:
    - `SyntheticRsIdp` — dataclass carrying the keypair + audience/issuer config
      + helpers for minting access tokens and simulating key rotation.
    - `build_synthetic_rs_idp(monkeypatch, ...)` — builder that registers the
      `fetch_data` patch and resets the RS's module-level JWKS-client cache.
    - Default constants (`DEFAULT_ISSUER`, `DEFAULT_AUDIENCE`, `DEFAULT_JWKS_URL`,
      `DEFAULT_KID`, `DEFAULT_ROTATED_KID`).
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from resource_server.auth import oidc_bearer

DEFAULT_ISSUER = "http://idp.test/realms/bmad-books"
DEFAULT_AUDIENCE = "bmad-books-resource-server"
DEFAULT_JWKS_URL = "http://idp.test/realms/bmad-books/protocol/openid-connect/certs"
DEFAULT_KID = "test-key-1"
DEFAULT_ROTATED_KID = "test-key-2"


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


def _public_jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    pn = key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": _int_to_b64u(pn.n),
        "e": _int_to_b64u(pn.e),
    }


@dataclass
class SyntheticRsIdp:
    """Test-side IdP — mints access tokens + provides JWKS to PyJWKClient."""

    private_key: rsa.RSAPrivateKey
    public_jwk: dict[str, str]
    issuer: str
    audience: str
    jwks_url: str
    kid: str
    # Rotation support — a second keypair/jwk that is added to the JWKS payload
    # via register_rotated_kid(); used to drive the "kid-miss → re-fetch" path.
    _alt_kid_jwk: dict[str, str] | None = None
    _alt_kid_private_key: rsa.RSAPrivateKey | None = None
    fetch_call_count: int = field(default=0)

    def make_access_token(
        self,
        *,
        sub: str = "test-subject-001",
        scope: str = "openid reading-speed:read",
        aud: str | list[str] | None = None,
        iss: str | None = None,
        exp_offset_seconds: int = 300,
        preferred_username: str | None = "testuser",
        signing_key: rsa.RSAPrivateKey | None = None,
        kid: str | None = None,
        alg: str = "RS256",
        claims_override: dict[str, Any] | None = None,
    ) -> str:
        """Sign and return an RS256 access token.

        Defaults match the synthetic IdP's issuer / audience / kid; pass overrides
        for negative-path tests (wrong aud/iss/exp, forged signature via a fresh
        keypair, missing required claim via claims_override={"sub": None}).

        `claims_override` semantics: a key with value `None` *deletes* the claim
        (used to drop required claims like `sub` / `exp`). Otherwise it adds /
        overwrites.
        """
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": iss if iss is not None else self.issuer,
            "aud": aud if aud is not None else self.audience,
            "sub": sub,
            "exp": now + exp_offset_seconds,
            "iat": now,
            "scope": scope,
        }
        if preferred_username is not None:
            claims["preferred_username"] = preferred_username
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
            algorithm=alg,
            headers={"kid": kid if kid is not None else self.kid},
        )

    def register_rotated_kid(
        self, new_kid: str = DEFAULT_ROTATED_KID
    ) -> rsa.RSAPrivateKey:
        """Add a second keypair to the JWKS payload (simulates key rotation).

        After calling, `make_access_token(kid=new_kid, signing_key=<returned>)`
        produces a token whose `kid` initially misses the cached JWKS and forces
        PyJWKClient to re-fetch.
        """
        alt_key = _generate_keypair()
        self._alt_kid_private_key = alt_key
        self._alt_kid_jwk = _public_jwk(alt_key, kid=new_kid)
        return alt_key

    @property
    def jwks_payload(self) -> dict[str, Any]:
        keys: list[dict[str, str]] = [self.public_jwk]
        if self._alt_kid_jwk is not None:
            keys.append(self._alt_kid_jwk)
        return {"keys": keys}


def build_synthetic_rs_idp(
    monkeypatch: pytest.MonkeyPatch,
    *,
    issuer: str = DEFAULT_ISSUER,
    audience: str = DEFAULT_AUDIENCE,
    jwks_url: str = DEFAULT_JWKS_URL,
    kid: str = DEFAULT_KID,
) -> SyntheticRsIdp:
    """Construct a SyntheticRsIdp and wire it up via monkeypatch.

    Performs three monkeypatches:
      1. Clears `oidc_bearer._jwks_clients` so cached clients from prior tests
         don't leak (cache_keys=True persists across tests otherwise).
      2. Patches `jwt.PyJWKClient.fetch_data` to return the IdP's JWKS payload
         (and increments `fetch_call_count` so tests can assert on cache hits
         / rotation re-fetches).
      3. Patches `settings.oidc_issuer_url` + `oidc_audience` in the RS's
         `core.config` module, and stashes a synthetic `OidcDiscovery` on
         `tests.conftest.app.state.oidc_discovery` carrying the IdP's
         `issuer` + `jwks_uri` so `_validate_access_token` resolves the
         synthetic values via the cached discovery doc (Story 7.2).
    """
    key = _generate_keypair()
    public_jwk = _public_jwk(key, kid=kid)
    idp = SyntheticRsIdp(
        private_key=key,
        public_jwk=public_jwk,
        issuer=issuer,
        audience=audience,
        jwks_url=jwks_url,
        kid=kid,
    )

    monkeypatch.setattr(oidc_bearer, "_jwks_clients", {})

    def _fetch_data(_self: jwt.PyJWKClient) -> dict[str, Any]:
        idp.fetch_call_count += 1
        return idp.jwks_payload

    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", _fetch_data)

    monkeypatch.setattr(oidc_bearer.settings, "oidc_issuer_url", issuer)
    monkeypatch.setattr(oidc_bearer.settings, "oidc_audience", audience)

    # Story 7.2: `_validate_access_token` reads jwks_uri + issuer from the
    # cached OidcDiscovery on app.state. Stash a synthetic discovery matching
    # the IdP's values; the autouse `_reset_app_state_discovery` fixture in
    # tests/conftest.py restores the default between tests.
    #
    # IMPORTANT: import `app` from `tests.conftest`, NOT from
    # `resource_server.main`. `tests/api/test_cors.py` reloads
    # `resource_server.main` mid-suite, which produces a new FastAPI app
    # instance bound on the module — but the `client` test fixture still
    # talks to the conftest-bound original. Setting state on the wrong app
    # would leave the request-side discovery stale.
    from resource_server.auth.oidc_discovery import OidcDiscovery
    from tests.conftest import app

    app.state.oidc_discovery = OidcDiscovery(
        issuer=issuer,
        authorization_endpoint=f"{issuer}/protocol/openid-connect/auth",
        token_endpoint=f"{issuer}/protocol/openid-connect/token",
        jwks_uri=jwks_url,
        end_session_endpoint=f"{issuer}/protocol/openid-connect/logout",
        revocation_endpoint=f"{issuer}/protocol/openid-connect/revoke",
    )

    return idp


def random_subject() -> str:
    """Convenience helper to mint a fresh-per-test subject UUID."""
    return "test-sub-" + uuid.uuid4().hex


__all__ = [
    "DEFAULT_AUDIENCE",
    "DEFAULT_ISSUER",
    "DEFAULT_JWKS_URL",
    "DEFAULT_KID",
    "DEFAULT_ROTATED_KID",
    "SyntheticRsIdp",
    "build_synthetic_rs_idp",
    "random_subject",
]
