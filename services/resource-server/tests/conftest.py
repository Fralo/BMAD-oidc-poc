import logging
import os

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

os.environ["ENV_FILE"] = ""
os.environ.setdefault("AUTH_TYPE", "none")
# Story 3.1 added required-fail-fast validators for OIDC_ISSUER_URL,
# OIDC_JWKS_URL, OIDC_AUDIENCE on AppSettings (mirrors the BFF's
# BFF_CLIENT_SECRET fail-fast pattern from Story 1.3 review's
# decision-needed #3). Provide non-secret pytest placeholders here so the
# settings instance built when `resource_server.main` is imported below
# validates successfully without leaking real values into pytest output.
os.environ.setdefault("OIDC_ISSUER_URL", "http://keycloak-test/realms/test")
os.environ.setdefault(
    "OIDC_JWKS_URL",
    "http://keycloak-test/realms/test/protocol/openid-connect/certs",
)
os.environ.setdefault("OIDC_AUDIENCE", "bmad-books-resource-server")

# Story 7.2: replace the lifespan's outbound discovery fetch with an
# in-process stub so AsyncClient(transport=ASGITransport(app=app)) startup
# does not try to reach a real Keycloak. The patch lands on the
# `resource_server.auth.oidc_discovery` module BEFORE `resource_server.main`
# is first imported, so the main module's `from ... import fetch_discovery`
# captures the stub (and survives an `importlib.reload`). Tests that need
# the real function (tests/auth/test_oidc_discovery.py) pull it via the
# preserved `_real_fetch_discovery` attribute below.
from resource_server.auth import oidc_discovery as _oidc_discovery_module
from resource_server.auth.oidc_discovery import OidcDiscovery

_TEST_DISCOVERY = OidcDiscovery(
    issuer="http://keycloak-test/realms/test",
    authorization_endpoint=(
        "http://keycloak-test/realms/test/protocol/openid-connect/auth"
    ),
    token_endpoint=("http://keycloak-test/realms/test/protocol/openid-connect/token"),
    jwks_uri=("http://keycloak-test/realms/test/protocol/openid-connect/certs"),
    end_session_endpoint=(
        "http://keycloak-test/realms/test/protocol/openid-connect/logout"
    ),
    revocation_endpoint=(
        "http://keycloak-test/realms/test/protocol/openid-connect/revoke"
    ),
)


async def _stub_fetch_discovery(*_args: object, **_kwargs: object) -> OidcDiscovery:
    return _TEST_DISCOVERY


_oidc_discovery_module._real_fetch_discovery = _oidc_discovery_module.fetch_discovery  # type: ignore[attr-defined]
_oidc_discovery_module.fetch_discovery = _stub_fetch_discovery  # type: ignore[assignment]

from resource_server.auth.dependencies import (  # noqa: E402  # patch must precede main import
    require_auth,
    require_role,
)
from resource_server.auth.models import Role  # noqa: E402
from resource_server.core.database import get_session  # noqa: E402
from resource_server.main import app  # noqa: E402

_stub_logger = logging.getLogger("resource_server.test_stubs")


class _StubPayload(BaseModel):
    value: str


_test_router = APIRouter(prefix="/test", tags=["Test Stubs"])
_require_admin_role = require_role(Role.ADMIN)


@_test_router.get("/open")
async def _stub_get_open() -> dict[str, str]:
    _stub_logger.debug("stub endpoint called")
    return {"status": "ok"}


@_test_router.post("/open", status_code=201)
async def _stub_post_open(payload: _StubPayload) -> dict[str, str]:
    return {"value": payload.value}


@_test_router.post("/auth-required", status_code=201)
async def _stub_post_auth_required(
    payload: _StubPayload,
    principal=Depends(require_auth),
) -> dict[str, str]:
    _ = principal
    return {"value": payload.value}


@_test_router.post("/admin-required", status_code=201)
async def _stub_post_admin_required(
    payload: _StubPayload,
    principal=Depends(_require_admin_role),
) -> dict[str, str]:
    _ = principal
    return {"value": payload.value}


app.include_router(_test_router)


@pytest.fixture(name="engine", scope="session")
async def engine_fixture():
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
        await engine.dispose()


@pytest.fixture(name="session")
async def session_fixture(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.fixture(name="client")
async def client_fixture(session):
    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()
