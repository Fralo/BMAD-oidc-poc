from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt
from jwt import PyJWK

from resource_server.auth.contracts import (
    AuthFeatureNotSupportedError,
    UnauthorizedError,
)
from resource_server.auth.models import AuthFunctions, Principal
from resource_server.auth.role_mapping import identity_role_mapper
from resource_server.core.config import AppSettings


def make_entra_auth(settings: AppSettings) -> AuthFunctions:
    """Return configured auth functions for the Entra (Azure AD) provider.

    State (JWKS cache, settings) is captured in closure scope — no class instance
    needed.
    """
    jwks_cache: dict[str, Any] | None = None
    jwks_cache_until = datetime.min.replace(tzinfo=UTC)
    jwks_cache_ttl_seconds = 300

    async def authenticate_bearer_token(token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError("Malformed bearer token") from exc

        alg = header.get("alg")
        if not isinstance(alg, str):
            raise UnauthorizedError("Missing token algorithm")

        jwks = await _get_jwks()
        signing_key = _select_signing_key(jwks, header.get("kid"))
        _validate_signing_key_metadata(signing_key, alg)
        claims = _decode_and_verify(token, signing_key, alg)

        iss = claims.get("iss")
        if settings.auth_external_issuer and iss != settings.auth_external_issuer:
            raise UnauthorizedError("Invalid token issuer")
        required_audience = settings.auth_external_audience
        if required_audience:
            aud = claims.get("aud")
            aud_match = (isinstance(aud, str) and aud == required_audience) or (
                isinstance(aud, list) and required_audience in aud
            )
            if not aud_match:
                raise UnauthorizedError("Invalid token audience")

        return _principal_from_claims(claims)

    async def get_client_credentials_access_token(scope: str) -> str:
        _require_client_credentials()
        form: dict[str, str] = {
            "client_id": settings.auth_external_client_id,
            "client_secret": settings.auth_external_client_secret,
            "grant_type": "client_credentials",
        }
        if scope:
            form["scope"] = scope
        return await _request_access_token(form)

    async def get_on_behalf_of_access_token(scope: str, user_token: str) -> str:
        _require_client_credentials()
        form: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": settings.auth_external_client_id,
            "client_secret": settings.auth_external_client_secret,
            "assertion": user_token,
            "scope": scope,
            "requested_token_use": "on_behalf_of",
        }
        return await _request_access_token(form)

    def _require_client_credentials() -> None:
        missing: list[str] = []
        if not settings.auth_external_client_id.strip():
            missing.append("auth_external_client_id")
        if not settings.auth_external_client_secret.strip():
            missing.append("auth_external_client_secret")
        if missing:
            raise AuthFeatureNotSupportedError(
                f"{', '.join(missing)} must be configured for this operation"
            )

    async def _request_access_token(form: dict[str, str]) -> str:
        if not settings.auth_external_token_uri:
            raise AuthFeatureNotSupportedError(
                "auth_external_token_uri is not configured"
            )
        body = await _http_post_form(settings.auth_external_token_uri, form)
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise UnauthorizedError("Token endpoint response missing access_token")
        return token

    async def _get_jwks() -> dict[str, Any]:
        nonlocal jwks_cache, jwks_cache_until
        now = datetime.now(UTC)
        if jwks_cache is not None and now < jwks_cache_until:
            return jwks_cache

        jwks_uri = await _resolve_jwks_uri()
        payload = await _http_get(jwks_uri)
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not isinstance(keys, list):
            raise UnauthorizedError("JWKS endpoint did not return a valid keys list")
        jwks_cache = payload
        jwks_cache_until = now + timedelta(seconds=jwks_cache_ttl_seconds)
        return payload

    async def _resolve_jwks_uri() -> str:
        if settings.auth_external_jwks_uri:
            return settings.auth_external_jwks_uri
        if not settings.auth_external_discovery_uri:
            raise UnauthorizedError(
                "Either auth_external_jwks_uri or auth_external_discovery_uri "
                "is required"
            )
        discovery = await _http_get(settings.auth_external_discovery_uri)
        jwks_uri = discovery.get("jwks_uri") if isinstance(discovery, dict) else None
        if not isinstance(jwks_uri, str) or not jwks_uri:
            raise UnauthorizedError("Discovery document missing jwks_uri")
        return jwks_uri

    async def _http_get(
        url: str,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        attempts = max(1, settings.auth_http_retry_attempts)
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=settings.auth_http_timeout_seconds
                ) as client:
                    response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise UnauthorizedError("Expected JSON object payload")
            except (httpx.HTTPError, ValueError, UnauthorizedError) as exc:
                last_error = exc
        raise UnauthorizedError("HTTP GET request failed") from last_error

    async def _http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
        attempts = max(1, settings.auth_http_retry_attempts)
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                async with httpx.AsyncClient(
                    timeout=settings.auth_http_timeout_seconds
                ) as client:
                    response = await client.post(url, data=data)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise UnauthorizedError("Expected JSON object payload")
            except (httpx.HTTPError, ValueError, UnauthorizedError) as exc:
                last_error = exc
        raise UnauthorizedError("HTTP POST request failed") from last_error

    return AuthFunctions(
        authenticate_bearer_token=authenticate_bearer_token,
        get_client_credentials_access_token=get_client_credentials_access_token,
        get_on_behalf_of_access_token=get_on_behalf_of_access_token,
        role_mapper=identity_role_mapper,
    )


def _select_signing_key(
    jwks_payload: dict[str, Any],
    kid: Any,
) -> dict[str, Any]:
    keys = jwks_payload.get("keys", [])
    if not isinstance(keys, list):
        raise UnauthorizedError("Invalid JWKS payload")
    for key in keys:
        if isinstance(key, dict) and kid and key.get("kid") == kid:
            return key
    if kid:
        raise UnauthorizedError(f"No signing key found for token kid={kid}")
    for key in keys:
        if isinstance(key, dict):
            return key
    raise UnauthorizedError("No signing key available in JWKS")


def _validate_signing_key_metadata(
    signing_key: dict[str, Any],
    alg: str,
) -> None:
    key_type = signing_key.get("kty")
    key_use = signing_key.get("use")
    if alg.startswith("RS") and key_type != "RSA":
        raise UnauthorizedError(
            f"Signing key type mismatch: alg={alg}, key.kty={key_type}"
        )
    if isinstance(key_use, str) and key_use.lower() != "sig":
        raise UnauthorizedError(f"JWKS key use is not signing: use={key_use}")


def _decode_and_verify(
    token: str,
    signing_key: dict[str, Any],
    alg: str,
) -> dict[str, Any]:
    try:
        jwk_data = {**signing_key}
        if "alg" not in jwk_data:
            jwk_data["alg"] = alg
        key = PyJWK(jwk_data).key
        return jwt.decode(
            token,
            key=key,
            algorithms=[alg],
            options={"verify_iss": False, "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired") from exc
    except jwt.ImmatureSignatureError as exc:
        raise UnauthorizedError("Token not yet valid") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid token signature") from exc


def _principal_from_claims(claims: dict[str, Any]) -> Principal:
    raw_roles = claims.get("roles", [])
    raw_groups = claims.get("groups", [])
    return Principal(
        subject=str(claims.get("sub", "")),
        user_id=str(claims.get("oid", claims.get("sub", ""))),
        name=str(claims["name"]) if "name" in claims else None,
        scope=str(claims["scp"]) if "scp" in claims else None,
        app_id=str(claims["appid"]) if "appid" in claims else None,
        roles=(
            [str(role) for role in raw_roles] if isinstance(raw_roles, list) else []
        ),
        groups=[str(group) for group in raw_groups]
        if isinstance(raw_groups, list)
        else [],
        claims=claims,
    )
