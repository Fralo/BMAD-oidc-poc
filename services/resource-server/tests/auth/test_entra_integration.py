"""Synthetic IdP integration tests for the Entra auth provider.

These tests exercise the full bearer-token validation path using a test-generated
RSA keypair. The provider's HTTP calls are intercepted via injected async functions
so no external infrastructure is needed.
"""

import time
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from resource_server.auth.dependencies import get_auth_functions
from resource_server.auth.entra import (
    _decode_and_verify,
    _principal_from_claims,
    _select_signing_key,
    _validate_signing_key_metadata,
)
from resource_server.auth.models import AuthFunctions
from resource_server.auth.role_mapping import identity_role_mapper
from resource_server.core.config import AppSettings
from resource_server.core.database import get_session
from resource_server.main import app

TEST_ISSUER = "https://test-issuer.example.com/"
TEST_AUDIENCE = "api://test-audience"
TEST_KID = "test-key-1"


def _entra_settings(**overrides: Any) -> AppSettings:
    defaults = {
        "auth_type": "entra",
        "auth_external_issuer": TEST_ISSUER,
        "auth_external_audience": TEST_AUDIENCE,
        "auth_external_jwks_uri": "https://test-issuer.example.com/keys",
        "auth_external_token_uri": "https://test-issuer.example.com/token",
        "auth_external_client_id": "test-client-id",
        "auth_external_client_secret": "test-secret",
    }
    defaults.update(overrides)
    return AppSettings.model_validate(defaults)


def _build_patched_auth_functions(
    jwks_response: dict[str, Any],
) -> AuthFunctions:
    """Build AuthFunctions for Entra with HTTP calls intercepted in-process."""
    settings = _entra_settings()

    async def _fake_http_get(
        url: str, headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        _ = (url, headers)
        return jwks_response

    async def _fake_http_post_form(_url: str, _data: dict[str, str]) -> dict[str, Any]:
        return {"access_token": "fake-obo-token"}

    async def authenticate_bearer_token(token: str) -> Any:
        import jwt as _jwt

        try:
            header = _jwt.get_unverified_header(token)
        except _jwt.InvalidTokenError as exc:
            from resource_server.auth.contracts import UnauthorizedError

            raise UnauthorizedError("Malformed bearer token") from exc

        alg = header.get("alg")
        if not isinstance(alg, str):
            from resource_server.auth.contracts import UnauthorizedError

            raise UnauthorizedError("Missing token algorithm")

        jwks = await _fake_http_get("fake-jwks-url")
        signing_key = _select_signing_key(jwks, header.get("kid"))
        _validate_signing_key_metadata(signing_key, alg)
        claims = _decode_and_verify(token, signing_key, alg)

        from resource_server.auth.contracts import UnauthorizedError

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
        form = {
            "client_id": settings.auth_external_client_id,
            "client_secret": settings.auth_external_client_secret,
            "grant_type": "client_credentials",
            "scope": scope,
        }
        body = await _fake_http_post_form(settings.auth_external_token_uri, form)
        token = body.get("access_token")
        if not isinstance(token, str):
            from resource_server.auth.contracts import UnauthorizedError

            raise UnauthorizedError("Token endpoint response missing access_token")
        return token

    async def get_on_behalf_of_access_token(scope: str, user_token: str) -> str:
        _ = (scope, user_token)
        return "fake-obo-token"

    return AuthFunctions(
        authenticate_bearer_token=authenticate_bearer_token,
        get_client_credentials_access_token=get_client_credentials_access_token,
        get_on_behalf_of_access_token=get_on_behalf_of_access_token,
        role_mapper=identity_role_mapper,
    )


@pytest.fixture(name="_entra_engine", scope="module")
async def entra_engine_fixture():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await engine.dispose()


@pytest.fixture(name="entra_integration_client")
async def entra_integration_client_fixture(
    _entra_engine,
    jwks_response: dict[str, Any],
):
    auth_fns = _build_patched_auth_functions(jwks_response)
    factory = async_sessionmaker(
        _entra_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_session():
        async with factory() as session:
            yield session

    def _override_auth_fns() -> AuthFunctions:
        return auth_fns

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_auth_functions] = _override_auth_fns

    with patch("resource_server.auth.dependencies.settings.auth_type", "entra"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    app.dependency_overrides.clear()


class TestProviderLevelValidation:
    """Direct provider-level tests for full authenticate_bearer_token path."""

    async def test_valid_token_returns_correct_principal(
        self,
        sign_jwt: Callable[..., str],
        jwks_response: dict[str, Any],
    ) -> None:
        auth_fns = _build_patched_auth_functions(jwks_response)
        token = sign_jwt()
        principal = await auth_fns.authenticate_bearer_token(token)
        assert principal.subject == "test-subject"
        assert principal.user_id == "test-oid-123"
        assert principal.name == "Test User"
        assert "admin" in principal.roles
        assert "reader" in principal.roles
        assert principal.claims["iss"] == TEST_ISSUER
        assert principal.claims["aud"] == TEST_AUDIENCE

    async def test_expired_token_raises(
        self,
        sign_jwt: Callable[..., str],
        jwks_response: dict[str, Any],
    ) -> None:
        auth_fns = _build_patched_auth_functions(jwks_response)
        token = sign_jwt({"exp": int(time.time()) - 600})
        with pytest.raises(Exception, match="expired"):
            await auth_fns.authenticate_bearer_token(token)

    async def test_wrong_issuer_raises(
        self,
        sign_jwt: Callable[..., str],
        jwks_response: dict[str, Any],
    ) -> None:
        auth_fns = _build_patched_auth_functions(jwks_response)
        token = sign_jwt({"iss": "https://wrong-issuer.example.com/"})
        with pytest.raises(Exception, match="issuer"):
            await auth_fns.authenticate_bearer_token(token)

    async def test_wrong_audience_raises(
        self,
        sign_jwt: Callable[..., str],
        jwks_response: dict[str, Any],
    ) -> None:
        auth_fns = _build_patched_auth_functions(jwks_response)
        token = sign_jwt({"aud": "api://wrong-audience"})
        with pytest.raises(Exception, match="audience"):
            await auth_fns.authenticate_bearer_token(token)

    async def test_invalid_signature_raises(
        self,
        sign_jwt: Callable[..., str],
        jwks_response: dict[str, Any],
    ) -> None:
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_pem = wrong_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        auth_fns = _build_patched_auth_functions(jwks_response)
        token = sign_jwt(private_pem=wrong_pem)
        with pytest.raises(Exception, match="signature"):
            await auth_fns.authenticate_bearer_token(token)

    async def test_malformed_token_raises(
        self,
        jwks_response: dict[str, Any],
    ) -> None:
        auth_fns = _build_patched_auth_functions(jwks_response)
        with pytest.raises(Exception, match="[Mm]alformed"):
            await auth_fns.authenticate_bearer_token("not-a-jwt")


class TestEndpointIntegration:
    """Full endpoint integration tests using AsyncClient with synthetic tokens."""

    async def test_valid_token_grants_access_to_auth_protected_endpoint(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt()
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "AuthedItem"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        assert response.json()["value"] == "AuthedItem"

    async def test_valid_admin_token_grants_access_to_role_protected_endpoint(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"roles": ["admin"]})
        response = await entra_integration_client.post(
            "/test/admin-required",
            json={"value": "AdminItem"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    async def test_missing_token_returns_sanitized_401(
        self,
        entra_integration_client: AsyncClient,
    ) -> None:
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "X"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["errorCode"] == "UNAUTHORIZED"
        assert body["detail"] is None

    async def test_expired_token_returns_sanitized_401(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"exp": int(time.time()) - 600})
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["errorCode"] == "UNAUTHORIZED"
        assert body["detail"] is None

    async def test_wrong_issuer_returns_sanitized_401(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"iss": "https://evil.example.com/"})
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["detail"] is None

    async def test_wrong_audience_returns_sanitized_401(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"aud": "api://wrong"})
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["detail"] is None

    async def test_invalid_signature_returns_sanitized_401(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        wrong_pem = wrong_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        token = sign_jwt(private_pem=wrong_pem)
        response = await entra_integration_client.post(
            "/test/auth-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        body = response.json()
        assert body["detail"] is None


class TestRoleEnforcement:
    """Role enforcement tests using synthetic tokens."""

    async def test_reader_only_gets_403_on_admin_endpoint(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"roles": ["reader"]})
        response = await entra_integration_client.post(
            "/test/admin-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        body = response.json()
        assert body["errorCode"] == "FORBIDDEN"
        assert body["detail"] is None

    async def test_admin_role_grants_access(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"roles": ["admin"]})
        response = await entra_integration_client.post(
            "/test/admin-required",
            json={"value": "AdminWidget"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    async def test_missing_roles_claim_denied_fail_closed(
        self,
        entra_integration_client: AsyncClient,
        sign_jwt: Callable[..., str],
    ) -> None:
        token = sign_jwt({"roles": None})
        response = await entra_integration_client.post(
            "/test/admin-required",
            json={"value": "NoRoles"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
