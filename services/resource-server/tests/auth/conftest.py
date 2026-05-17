import base64
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from resource_server.auth.contracts import UnauthorizedError
from resource_server.auth.models import AuthFunctions, Principal
from resource_server.core.database import get_session
from resource_server.main import app


def _int_to_base64url(n: int) -> str:
    b = n.to_bytes((n.bit_length() + 7) // 8, byteorder="big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


TEST_ISSUER = "https://test-issuer.example.com/"
TEST_AUDIENCE = "api://test-audience"
TEST_KID = "test-key-1"


@pytest.fixture(name="rsa_keypair", scope="module")
def rsa_keypair_fixture() -> dict[str, Any]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_numbers = private_key.public_key().public_numbers()
    return {
        "private_pem": private_pem,
        "n": _int_to_base64url(pub_numbers.n),
        "e": _int_to_base64url(pub_numbers.e),
    }


@pytest.fixture(name="jwks_response")
def jwks_response_fixture(rsa_keypair: dict[str, Any]) -> dict[str, Any]:
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": TEST_KID,
                "use": "sig",
                "alg": "RS256",
                "n": rsa_keypair["n"],
                "e": rsa_keypair["e"],
            }
        ]
    }


@pytest.fixture(name="sign_jwt")
def sign_jwt_fixture(rsa_keypair: dict[str, Any]):
    def _sign(
        claims: dict[str, Any] | None = None,
        *,
        kid: str = TEST_KID,
        algorithm: str = "RS256",
        private_pem: str | None = None,
    ) -> str:
        now = int(time.time())
        default_claims: dict[str, Any] = {
            "sub": "test-subject",
            "oid": "test-oid-123",
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "name": "Test User",
            "exp": now + 3600,
            "nbf": now - 60,
            "iat": now,
            "roles": ["admin", "reader"],
        }
        if claims:
            default_claims.update(claims)
        return jwt.encode(
            default_claims,
            private_pem or rsa_keypair["private_pem"],
            algorithm=algorithm,
            headers={"kid": kid},
        )

    return _sign


@pytest.fixture(name="entra_engine", scope="module")
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


@pytest.fixture(name="entra_client")
async def entra_client_fixture(entra_engine):
    """Client with auth_type patched to 'entra' so auth-error paths execute."""
    factory = async_sessionmaker(
        entra_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session

    with patch(
        "resource_server.auth.dependencies.settings.auth_type",
        "entra",
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    app.dependency_overrides.clear()


def _noop_role_mapper(role: str) -> str:
    return role


def mock_auth_functions_unauthorized() -> AuthFunctions:
    err = UnauthorizedError("JWKS endpoint did not return a valid keys list")
    mock = AsyncMock(side_effect=err)
    return AuthFunctions(
        authenticate_bearer_token=mock,
        get_client_credentials_access_token=AsyncMock(),
        get_on_behalf_of_access_token=AsyncMock(),
        role_mapper=_noop_role_mapper,
    )


def mock_auth_functions_unexpected_error() -> AuthFunctions:
    mock = AsyncMock(
        side_effect=RuntimeError(
            "https://login.microsoftonline.com/.well-known/openid-configuration"
        )
    )
    return AuthFunctions(
        authenticate_bearer_token=mock,
        get_client_credentials_access_token=AsyncMock(),
        get_on_behalf_of_access_token=AsyncMock(),
        role_mapper=_noop_role_mapper,
    )


def mock_auth_functions_reader_principal() -> AuthFunctions:
    principal = Principal(
        subject="user-1",
        user_id="user-1",
        name="Test User",
        roles=["reader"],
    )
    return AuthFunctions(
        authenticate_bearer_token=AsyncMock(return_value=principal),
        get_client_credentials_access_token=AsyncMock(),
        get_on_behalf_of_access_token=AsyncMock(),
        role_mapper=_noop_role_mapper,
    )
