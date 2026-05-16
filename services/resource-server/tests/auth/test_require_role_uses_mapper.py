from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
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
from resource_server.core.config import AppSettings
from resource_server.core.database import get_session
from resource_server.main import app

TEST_ISSUER = "https://test-issuer.example.com/"
TEST_AUDIENCE = "api://test-audience"
TEST_KID = "test-key-1"


def _guid_role_mapper(role: str) -> str:
    mapping = {
        "admin": "guid-admin-001",
        "writer": "guid-writer-002",
        "reader": "guid-reader-003",
    }
    return mapping.get(role, role)


def _build_guid_mapped_auth_functions(
    jwks_response: dict[str, Any],
) -> AuthFunctions:
    settings = AppSettings(
        auth_type="entra",
        auth_external_issuer=TEST_ISSUER,
        auth_external_audience=TEST_AUDIENCE,
        auth_external_jwks_uri="https://test-issuer.example.com/keys",
        auth_external_token_uri="https://test-issuer.example.com/token",
        auth_external_client_id="test-client-id",
        auth_external_client_secret="test-secret",
    )

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

        signing_key = _select_signing_key(jwks_response, header.get("kid"))
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

    return AuthFunctions(
        authenticate_bearer_token=authenticate_bearer_token,
        get_client_credentials_access_token=AsyncMock(return_value="fake-token"),
        get_on_behalf_of_access_token=AsyncMock(return_value="fake-obo-token"),
        role_mapper=_guid_role_mapper,
    )


class TestRequireRoleUsesMapper:
    """Verify that require_role goes through role_mapper for the comparison."""

    @pytest.fixture(name="_guid_engine", scope="module")
    async def guid_engine_fixture(self):
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

    @pytest.fixture(name="guid_client")
    async def guid_client_fixture(self, _guid_engine, sign_jwt, jwks_response):
        """Client using a GUID role mapper where 'admin' -> 'guid-admin-001'."""
        auth_fns = _build_guid_mapped_auth_functions(jwks_response)
        factory = async_sessionmaker(
            _guid_engine, class_=AsyncSession, expire_on_commit=False
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

    async def test_guid_mapped_role_grants_access(
        self,
        guid_client: AsyncClient,
        sign_jwt,
    ) -> None:
        token = sign_jwt({"roles": ["guid-admin-001"]})
        response = await guid_client.post(
            "/test/admin-required",
            json={"value": "GuidAdmin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201

    async def test_unmapped_admin_string_denied_with_guid_mapper(
        self,
        guid_client: AsyncClient,
        sign_jwt,
    ) -> None:
        token = sign_jwt({"roles": ["admin"]})
        response = await guid_client.post(
            "/test/admin-required",
            json={"value": "X"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
