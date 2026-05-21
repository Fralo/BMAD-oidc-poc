import logging
import os
import re

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
# Story 3.5 review CR9: OIDC_ISSUER_URL is required-fail-fast so the
# BFF→Keycloak refresh-token call (ResourceServerClient._refresh_access_token)
# cannot silently emit a relative URL on a misconfigured deployment.
os.environ.setdefault("OIDC_ISSUER_URL", "http://keycloak:8080/realms/test")

# Story 7.2: replace the lifespan's outbound discovery fetch with an
# in-process stub so AsyncClient(transport=ASGITransport(app=app)) startup
# does not try to reach a real Keycloak. The patch lands on the
# `bff.auth.oidc_discovery` module BEFORE `bff.main` is first imported, so
# bff.main's `from ... import fetch_discovery` captures the stub. This also
# survives `importlib.reload(bff.main)` (used by tests/api/test_cors.py).
# Tests that need the real function (tests/auth/test_oidc_discovery.py)
# pull it via the preserved `_real_fetch_discovery` attribute below.
from bff.auth import oidc_discovery as _oidc_discovery_module
from bff.auth.oidc_discovery import OidcDiscovery

_TEST_DISCOVERY = OidcDiscovery(
    issuer="http://idp.test/realms/test",
    authorization_endpoint=("http://idp.test/realms/test/protocol/openid-connect/auth"),
    token_endpoint=("http://idp.test/realms/test/protocol/openid-connect/token"),
    jwks_uri=("http://idp.test/realms/test/protocol/openid-connect/certs"),
    end_session_endpoint=("http://idp.test/realms/test/protocol/openid-connect/logout"),
    revocation_endpoint=("http://idp.test/realms/test/protocol/openid-connect/revoke"),
)


async def _stub_fetch_discovery(*_args: object, **_kwargs: object) -> OidcDiscovery:
    return _TEST_DISCOVERY


_oidc_discovery_module._real_fetch_discovery = _oidc_discovery_module.fetch_discovery  # type: ignore[attr-defined]
_oidc_discovery_module.fetch_discovery = _stub_fetch_discovery  # type: ignore[assignment]

from bff.core.config import settings  # noqa: E402  # patch must precede bff.main import
from bff.core.database import get_session  # noqa: E402
from bff.main import app  # noqa: E402

# Story 7.2: httpx.ASGITransport (the one used in tests) does NOT run lifespan
# by default, so the lifespan-populated `app.state.oidc_discovery` is empty
# when tests issue requests. Set it directly so route handlers depending on
# `get_oidc_discovery` resolve. Tests that exercise the lifespan-fails-fast
# path explicitly invoke `app.router.lifespan_context(app)` in their own
# `async with` (after re-stubbing `fetch_discovery` to raise).
app.state.oidc_discovery = _TEST_DISCOVERY

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
    """Like `client`, but pre-seeded with the `csrf_token` cookie + `X-CSRF-Token`
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
    try:
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
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Story 7.3 AC5 — static analysis on every `emit_auth_decision` call.
#
# The helper at `bff.aop.auth_logging` is the only code path that emits the
# ACME-schema {timestamp, sub, decision, reason} wire record. Attaching a
# logging.Handler to that logger lets every existing test in the suite
# re-assert the schema invariant ("no token material in `reason`") for free.
# ---------------------------------------------------------------------------

_AUTH_DECISION_LOGGER = "bff.aop.auth_logging"
# OAuth concept identifiers MUST be matched with word boundaries: the legitimate
# reasons `id_token_missing` / `id_token_invalid` etc. are concept names, NOT
# leaked token values. `\b` between `id_token` and `_invalid` is suppressed
# because `_` is a word char, so `\bid_token\b` only matches `id_token` as a
# free-standing identifier (e.g. `id_token=eyJ...`), not as a prefix in a
# compound reason. The two non-word-bounded patterns — `Bearer ` (with trailing
# space) and `eyJ` (JWT header prefix) — keep their literal-substring semantics.
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
    """Validate every auth-decision record before any other handler sees it.

    Asserts that the `reason` string does not carry token *material* — a
    literal `access_token` / `refresh_token` / `id_token` standalone (token
    field name preceding a value), a `Bearer ` prefix, an `eyJ` JWT-header
    prefix, or a JWT-shaped / long-base64url-ish substring. OAuth concept
    identifiers used inside compound reasons (`id_token_invalid`,
    `token_exchange_failed`) are allowed.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if not hasattr(record, "decision"):
            return
        # Validate BOTH `reason` and `sub` — the helper truncates `sub` to
        # first-8 + ellipsis, but those 8 chars are still observable on the
        # wire, so an `eyJ` JWT-header prefix surfacing as a leaked `sub`
        # would defeat the schema invariant unless we also check this field
        # (review-fix P2).
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
