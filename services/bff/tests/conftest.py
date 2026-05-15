import logging
import os

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

os.environ["ENV_FILE"] = ""
# BFF_CLIENT_SECRET is required-fail-fast at AppSettings construction (Story
# 1.3 Review Findings D3). Provide a non-secret placeholder here so the test
# settings instance — built when `bff.main` is imported below — validates
# successfully without leaking a real secret into pytest output.
os.environ.setdefault("BFF_CLIENT_SECRET", "pytest-placeholder")
# Story 1.5 added OIDC_AUTHORIZE_URL_BROWSER as a required-fail-fast config var
# (browser-vs-container hostname split — see deferred-work.md#D2/#D8). Provide
# a stable default here so the test settings instance — built when `bff.main`
# is imported below — validates successfully.
os.environ.setdefault("OIDC_AUTHORIZE_URL_BROWSER", "http://localhost:8080/realms/test")

from bff.core.config import settings
from bff.core.database import get_session
from bff.main import app

# Shared CSRF secret for state-changing-request fixtures. 43 chars matches the
# real `secrets.token_urlsafe(32)` output length minted by Story 1.5 at
# /auth/callback — keeps the test surface honest against any future regression
# that adds a length-based short-circuit ahead of `hmac.compare_digest`.
_CSRF_FIXTURE_VALUE = "test-csrf-secret-43chars-xxxxxxxxxxxxxxxxxxx"

_stub_logger = logging.getLogger("bff.test_stubs")


class _StubPayload(BaseModel):
    value: str


_test_router = APIRouter(prefix="/test", tags=["Test Stubs"])


@_test_router.get("/open")
async def _stub_get_open() -> dict[str, str]:
    _stub_logger.debug("stub endpoint called")
    return {"status": "ok"}


@_test_router.post("/open", status_code=201)
async def _stub_post_open(payload: _StubPayload) -> dict[str, str]:
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


@pytest.fixture(name="client_with_csrf")
async def client_with_csrf_fixture(session, monkeypatch: pytest.MonkeyPatch):
    """Like `client`, but pre-seeded with the `bff_csrf` cookie + `X-CSRF-Token`
    header + same-origin `Origin` so state-changing requests pass the CSRF
    middleware introduced in Story 1.6.

    Also patches `settings.bff_base_url` to `http://test` so the middleware's
    same-origin check accepts the AsyncClient's `base_url`. monkeypatch is
    function-scoped; the patch unwinds between tests.
    """
    monkeypatch.setattr(settings, "bff_base_url", "http://test")

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={settings.bff_csrf_cookie_name: _CSRF_FIXTURE_VALUE},
        headers={
            "X-CSRF-Token": _CSRF_FIXTURE_VALUE,
            "Origin": "http://test",
        },
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(name="client_no_redirects")
async def client_no_redirects_fixture(session):
    """Like `client`, but with `follow_redirects=False` so 302 responses from
    /auth/login and /auth/callback are inspectable rather than auto-followed.
    """

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as c:
        yield c
    app.dependency_overrides.clear()
