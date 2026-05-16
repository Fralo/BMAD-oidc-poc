"""JWKS-validated OIDC bearer auth plugin for the BMAD_books Resource Server.

Validates RS256-signed access tokens against the Keycloak JWKS, enforces the
issuer + audience claims, and exposes `require_scope(scope)` as a FastAPI
dependency factory for endpoint-level scope gating.

The module-level `_jwks_clients` dict caches a `jwt.PyJWKClient` per JWKS URL
so `cache_keys=True` actually persists across requests (the BFF's
`keycloak_cookie_session.py` uses the same pattern — keep them in sync for
cross-service consistency).

Public surface:
    - `bearer_scheme` — FastAPI `HTTPBearer` (auto_error=False).
    - `get_authenticated_principal` — async dependency returning `Principal`.
    - `require_scope(scope)` — dependency factory enforcing JWT scope membership.
    - `make_oidc_bearer_auth(settings)` — archetype-seam factory returning
      `AuthFunctions` for the `oidc_bearer` mode.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from resource_server.auth.contracts import (
    AuthFeatureNotSupportedError,
    UnauthorizedError,
)
from resource_server.auth.models import AuthFunctions, Principal
from resource_server.auth.role_mapping import identity_role_mapper
from resource_server.core.config import AppSettings, settings
from resource_server.core.errors import AppException, ErrorCode

logger = logging.getLogger(__name__)


# Module-level cache keyed by JWKS URL so `cache_keys=True` actually persists
# across requests. PyJWKClient.get_signing_key_from_jwt uses synchronous urllib
# internally; that call is infrequent (key cache hit on most requests) but
# callers should be aware it blocks the event loop on a cache miss. Architecture
# line 415 mandates a 24h cache TTL; PyJWKClient does not expose a TTL knob —
# the kid-miss re-fetch path satisfies the underlying invariant (validation
# survives key rotation without operator intervention).
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def _get_jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = jwt.PyJWKClient(
            jwks_url, cache_keys=True, max_cached_keys=4
        )
    return _jwks_clients[jwks_url]


def _parse_scopes(claim: object) -> frozenset[str]:
    if isinstance(claim, str):
        return frozenset(s for s in claim.split() if s)
    return frozenset()


def _validate_access_token(token: str) -> dict[str, Any]:
    try:
        jwks_client = _get_jwks_client(settings.oidc_jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
            options={"require": ["iss", "aud", "exp", "sub"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as exc:
        logger.warning("JWT validation failed: %s", type(exc).__name__)
        raise AppException(ErrorCode.SESSION_EXPIRED) from exc
    if not isinstance(decoded, dict):  # pragma: no cover -- PyJWT always returns dict
        raise AppException(ErrorCode.SESSION_EXPIRED)
    return decoded


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    scope_raw = claims.get("scope")
    return Principal(
        subject=str(claims["sub"]),
        user_id=str(claims["sub"]),
        name=str(claims["preferred_username"])
        if "preferred_username" in claims
        else None,
        scope=str(scope_raw) if isinstance(scope_raw, str) else None,
        scopes=_parse_scopes(scope_raw),
        claims=claims,
    )


bearer_scheme = HTTPBearer(auto_error=False)


async def get_authenticated_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException(ErrorCode.SESSION_EXPIRED)
    token = credentials.credentials
    if not token or not token.strip():
        raise AppException(ErrorCode.SESSION_EXPIRED)
    claims = _validate_access_token(token)
    return _principal_from_claims(claims)


def require_scope(scope: str) -> Callable[..., Awaitable[Principal]]:
    async def _dependency(
        principal: Annotated[Principal, Depends(get_authenticated_principal)],
    ) -> Principal:
        if scope not in principal.scopes:
            logger.warning(
                "Scope check failed: sub=%s requires %s",
                principal.subject,
                scope,
            )
            raise AppException(ErrorCode.FORBIDDEN_SCOPE)
        return principal

    return _dependency


def make_oidc_bearer_auth(settings_arg: AppSettings) -> AuthFunctions:
    """Return configured auth functions for the OIDC bearer (Keycloak JWKS) provider.

    The signature accepts `AppSettings` for parity with `make_entra_auth` and to
    keep the archetype's factory seam clean — but the module's deps read from
    the module-level `settings` singleton so test fixtures can monkeypatch them
    without rebuilding the AuthFunctions closure.
    """
    _ = settings_arg

    async def authenticate_bearer_token(token: str) -> Principal:
        try:
            claims = _validate_access_token(token)
        except AppException as exc:
            raise UnauthorizedError("JWT validation failed") from exc
        return _principal_from_claims(claims)

    async def get_client_credentials_access_token(scope: str) -> str:
        _ = scope
        raise AuthFeatureNotSupportedError(
            "Token issuance is not supported by AUTH_TYPE=oidc_bearer"
        )

    async def get_on_behalf_of_access_token(scope: str, user_token: str) -> str:
        _ = (scope, user_token)
        raise AuthFeatureNotSupportedError(
            "OBO flow is not supported by AUTH_TYPE=oidc_bearer"
        )

    return AuthFunctions(
        authenticate_bearer_token=authenticate_bearer_token,
        get_client_credentials_access_token=get_client_credentials_access_token,
        get_on_behalf_of_access_token=get_on_behalf_of_access_token,
        role_mapper=identity_role_mapper,
    )
