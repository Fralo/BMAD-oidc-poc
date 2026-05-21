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
from resource_server.auth.oidc_discovery import OidcDiscovery, get_oidc_discovery
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
    # Keycloak emits `scope` as a space-delimited string; other IdPs (Auth0,
    # Okta) emit it as a JSON array. If oidc_bearer is ever pointed at one of
    # those, every request would silently 403 without any signal. Log so that
    # misconfiguration is observable; consumers can extend _parse_scopes to
    # accept lists when that need lands.
    if claim is not None:
        logger.warning(
            "scope claim was non-string (%s); falling back to empty scope set",
            type(claim).__name__,
        )
    return frozenset()


def _validate_access_token(token: str, discovery: OidcDiscovery) -> dict[str, Any]:
    try:
        jwks_client = _get_jwks_client(discovery.jwks_uri)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.oidc_audience,
            issuer=discovery.issuer,
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
    # `sub` is enforced by the `require` list in _validate_access_token, but
    # default to "" defensively so a future edit to the require list cannot
    # surface as a 500 KeyError — the surrounding code maps an empty subject
    # to a normal SESSION_EXPIRED if it ever leaks through.
    sub = str(claims.get("sub", ""))
    return Principal(
        subject=sub,
        user_id=sub,
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
    discovery: Annotated[OidcDiscovery, Depends(get_oidc_discovery)],
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AppException(ErrorCode.SESSION_EXPIRED)
    token = credentials.credentials
    if not token or not token.strip():
        raise AppException(ErrorCode.SESSION_EXPIRED)
    claims = _validate_access_token(token, discovery)
    return _principal_from_claims(claims)


def require_scope(scope: str) -> Callable[..., Awaitable[Principal]]:
    # Fail fast at factory-call time on empty / whitespace-padded scope strings.
    # A typo like `require_scope(" reading-speed:read")` (leading space) would
    # never match any parsed JWT scope (which `_parse_scopes` whitespace-cleans),
    # silently 403ing every caller. Better to surface as an ImportError-like
    # explosion at module load than a quiet authorization failure at request
    # time.
    if not scope or scope != scope.strip():
        msg = (
            f"require_scope() expects a non-empty, non-whitespace-padded scope; "
            f"got {scope!r}"
        )
        raise ValueError(msg)

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


def make_oidc_bearer_auth(
    settings_arg: AppSettings, discovery: OidcDiscovery
) -> AuthFunctions:
    """Return configured auth functions for the OIDC bearer (Keycloak JWKS) provider.

    Story 7.2: `discovery` is the cached OIDC discovery doc; the closure
    captures it so JWT validation reads `jwks_uri` + `issuer` from the
    doc instead of dead env vars. The `settings_arg` parameter is kept
    for archetype-seam parity with `make_entra_auth`.
    """
    _ = settings_arg

    async def authenticate_bearer_token(token: str) -> Principal:
        try:
            claims = _validate_access_token(token, discovery)
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
