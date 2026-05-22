import logging
import os
import re

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

os.environ["ENV_FILE"] = ""
os.environ.setdefault("AUTH_TYPE", "none")
# Story 3.1 + 7.2: required-fail-fast validators for OIDC_ISSUER_URL +
# OIDC_AUDIENCE (OIDC_JWKS_URL removed by Story 7.2 — JWKS now read from
# the cached discovery doc). Provide non-secret pytest placeholders so the
# settings instance built when `resource_server.main` is imported below
# validates successfully without leaking real values into pytest output.
os.environ.setdefault("OIDC_ISSUER_URL", "http://keycloak-test/realms/test")
os.environ.setdefault("OIDC_AUDIENCE", "bmad-books-resource-server")

# Story 7.2: replace the lifespan's outbound discovery fetch with an
# in-process stub so AsyncClient(transport=ASGITransport(app=app)) startup
# does not try to reach a real Keycloak. The patch lands on the
# `resource_server.auth.oidc_discovery` module BEFORE `resource_server.main`
# is first imported, so the main module's `from ... import fetch_discovery`
# captures the stub (and survives an `importlib.reload`). Tests that need
# the real function import `_real_fetch_discovery` directly from the source
# module — it's defined there as a stable alias.
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


_oidc_discovery_module.fetch_discovery = _stub_fetch_discovery  # type: ignore[assignment]

from resource_server.auth.dependencies import (  # noqa: E402  # patch must precede main import
    require_auth,
    require_role,
)
from resource_server.auth.models import Role  # noqa: E402
from resource_server.core.database import get_session  # noqa: E402
from resource_server.main import app  # noqa: E402

# Story 7.2: ASGITransport doesn't run lifespan; populate app.state directly.
app.state.oidc_discovery = _TEST_DISCOVERY


@pytest.fixture(autouse=True)
def _reset_app_state_discovery():
    """Re-stash the default OidcDiscovery on app.state for each test.

    Story 7.2: the synthetic IdP fixture mutates `app.state.oidc_discovery`
    so JWT validation sees the synthetic JWKS/issuer. Without this reset,
    a non-synthetic-IdP test that runs afterward would inherit the leftover
    state and fail on issuer/audience checks.
    """
    app.state.oidc_discovery = _TEST_DISCOVERY
    yield
    app.state.oidc_discovery = _TEST_DISCOVERY


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


# ---------------------------------------------------------------------------
# Story 7.3 AC5 — static analysis on every `emit_auth_decision` call.
#
# The helper at `resource_server.aop.auth_logging` is the only code path that
# emits the ACME-schema {timestamp, sub, decision, reason} wire record.
# Attaching a logging.Handler to that logger lets every existing test in the
# suite re-assert the schema invariant ("no token material in `reason`") for
# free.
# ---------------------------------------------------------------------------

_AUTH_DECISION_LOGGER = "resource_server.aop.auth_logging"
# Word-bounded matching for OAuth concept identifiers so legitimate compound
# reasons like `id_token_invalid` / `token_exchange_failed` are not false
# positives. See BFF conftest for the full rationale.
_BANNED_REGEXES = (
    re.compile(r"\baccess_token\b"),
    re.compile(r"\brefresh_token\b"),
    re.compile(r"\bid_token\b"),
    re.compile(r"Bearer "),
    re.compile(r"eyJ"),
)
_JWT_SHAPE_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_BASE64URLISH_RE = re.compile(r"[A-Za-z0-9_-]{33,}")


class _AuthDecisionAssertHandler(logging.Handler):
    """Validate every auth-decision record before any other handler sees it."""

    def emit(self, record: logging.LogRecord) -> None:
        if not hasattr(record, "decision"):
            return
        # Validate BOTH `reason` and `sub` (review-fix P2 — see BFF conftest
        # for the full rationale).
        for field_name in ("reason", "sub"):
            value = getattr(record, field_name, None)
            if value is None:
                continue
            assert isinstance(value, str), (
                f"emit_auth_decision: {field_name} must be str|None, "
                f"got {type(value).__name__}"
            )
            for pattern in _BANNED_REGEXES:
                assert not pattern.search(value), (
                    f"emit_auth_decision: {field_name} matches token-material "
                    f"pattern {pattern.pattern!r}: {value!r}"
                )
            assert not _JWT_SHAPE_RE.search(value), (
                f"emit_auth_decision: {field_name} looks like a JWT: {value!r}"
            )
            assert not _BASE64URLISH_RE.search(value), (
                f"emit_auth_decision: {field_name} carries a long base64url-ish "
                f"substring (>32 chars): {value!r}"
            )


@pytest.fixture(scope="session", autouse=True)
def _assert_no_token_material_in_auth_decisions():
    """Install the AC5 static-analysis handler for the test-suite lifetime."""
    handler = _AuthDecisionAssertHandler(level=logging.DEBUG)
    target = logging.getLogger(_AUTH_DECISION_LOGGER)
    target.addHandler(handler)
    try:
        yield
    finally:
        target.removeHandler(handler)


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
