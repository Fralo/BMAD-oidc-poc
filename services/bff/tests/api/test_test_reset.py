"""Route-level tests for `/v1/test/reset` and `/v1/test/session-debug`.

POST `/v1/test/reset` (Story 1.12): gating, bearer auth, truncation,
CSRF exemption, OpenAPI exposure, startup-log signaling. Post-review
hardening regressions for the trailing-slash CSRF exemption (Patch P2)
and DB-failure honest-degradation envelope (Patch P6) are also covered.

GET `/v1/test/session-debug` (Story 1.13): gating, bearer auth, cookie
lookup (200 happy path / 404 missing-cookie / 404 unknown-session-id),
no-leak log assertions (refresh_token and full session_id never appear
in any log line), OpenAPI exposure.

The production module under test is `bff.api.test_reset`; this file is
named `test_test_reset.py` (doubled `test_` prefix) so pytest discovers
it without colliding with the module name.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from bff.api.auth import router as auth_router
from bff.api.health import router as health_router
from bff.api.me import router as me_router
from bff.api.test_reset import register_test_reset_router
from bff.api.v1 import router as v1_router
from bff.auth.csrf import CsrfMiddleware
from bff.core.config import settings
from bff.core.database import get_session
from bff.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from bff.models import entities

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_TOKEN = "secret-xyz"
_UNAUTHORIZED_BODY = {
    "errorCode": "session_expired",
    "message": "Session expired or not present",
    "detail": None,
}


def _build_app(*, enable: bool, token: str) -> FastAPI:
    """Build a fresh FastAPI app whose `enable_test_reset` / `test_reset_token`
    values are evaluated AT REGISTRATION TIME (not at import time).

    Mirrors the construction in `bff/main.py` but skips CORS (the test
    suite doesn't exercise it from here) and crucially patches the global
    `settings` instance BEFORE calling `register_test_reset_router` so the
    gate evaluation sees the test-supplied values.

    The CSRF middleware is wired in to exercise scenario #15 (exemption
    must actually fire on a real app, not on a mocked one). Story 6.4
    removed the CSP-attachment middleware from this helper (CSP source
    moved to the SPA SSR edge per architecture A8 amendment).
    """
    # We deliberately mutate the global settings singleton — the helper's
    # caller is expected to restore via `monkeypatch.setattr` (which we
    # use throughout). Snapshot here only to keep call-site explicit.
    settings.enable_test_reset = enable
    settings.test_reset_token = token

    app = FastAPI(title="bff-test", lifespan=None)
    app.add_middleware(CsrfMiddleware)  # ty: ignore[invalid-argument-type]
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(health_router)
    app.include_router(me_router)
    app.include_router(auth_router)
    app.include_router(v1_router)
    register_test_reset_router(app, settings)
    return app


class _AppContext:
    """Bundles a fresh app, engine, sessionmaker, and a dependency-overriding
    `client()` factory so each test can build its own world.
    """

    def __init__(self, app: FastAPI, engine, factory) -> None:
        self.app = app
        self.engine = engine
        self.factory = factory

    def make_client(self) -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=self.app),
            base_url="http://test",
        )


async def _build_context(*, enable: bool, token: str) -> _AppContext:
    """Build a fresh app + in-memory SQLite engine + session factory.

    Wires `get_session` via `app.dependency_overrides` so each request
    gets a session bound to the per-test engine.
    """
    app = _build_app(enable=enable, token=token)
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override
    return _AppContext(app, engine, factory)


async def _seed_session_row(ctx: _AppContext, *, suffix: str) -> None:
    async with ctx.factory() as db:
        row = entities.Session(
            id=f"seeded-session-{suffix}",
            sub=f"sub-{suffix}",
            access_token="at",
            refresh_token="rt",
            id_token="it",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            csrf_secret="cs",
        )
        db.add(row)
        await db.commit()


async def _seed_auth_state_row(ctx: _AppContext, *, suffix: str) -> None:
    async with ctx.factory() as db:
        row = entities.AuthState(
            id=f"seeded-auth-{suffix}",
            code_verifier="cv",
            state=f"state-{suffix}",
            nonce=f"nonce-{suffix}",
            return_to=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(row)
        await db.commit()


async def _seed_book_row(ctx: _AppContext, *, suffix: str) -> None:
    async with ctx.factory() as db:
        row = entities.Book(
            sub=f"sub-{suffix}",
            title=f"Book {suffix}",
            pages=100,
            # status defaults to "to-read"
        )
        db.add(row)
        await db.commit()


async def _count_sessions(ctx: _AppContext) -> int:
    async with ctx.factory() as db:
        result = await db.execute(select(entities.Session))
        return len(result.scalars().all())


async def _count_auth_states(ctx: _AppContext) -> int:
    async with ctx.factory() as db:
        result = await db.execute(select(entities.AuthState))
        return len(result.scalars().all())


async def _count_books(ctx: _AppContext) -> int:
    async with ctx.factory() as db:
        result = await db.execute(select(entities.Book))
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Scenarios 1–3: route NOT registered when gate fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
async def test_scenario_1_route_not_registered_when_gate_off(
    method: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1: ENABLE_TEST_RESET=false → 404 on every method."""
    monkeypatch.setattr(settings, "enable_test_reset", False)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=False, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.request(
                method,
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 404
    finally:
        await ctx.engine.dispose()


async def test_scenario_2_route_not_registered_when_token_empty(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#2: gate ON but token is "" → 404 and WARN log fires."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", "")
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token="")
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": "Bearer anything"},
            )
        assert response.status_code == 404
        assert any("test_reset_route_skipped" in r.message for r in caplog.records)
    finally:
        await ctx.engine.dispose()


async def test_scenario_3_route_not_registered_when_token_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#3: gate ON but token is "   " → 404 and WARN log fires."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", "   ")
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token="   ")
    try:
        async with ctx.make_client() as client:
            response = await client.post("/v1/test/reset")
        assert response.status_code == 404
        assert any("test_reset_route_skipped" in r.message for r in caplog.records)
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Scenarios 4–10: bearer auth failure modes
# ---------------------------------------------------------------------------


async def test_scenario_4_missing_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#4: no Authorization header → 401 missing_header; no DB writes."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        await _seed_session_row(ctx, suffix="4")
        async with ctx.make_client() as client:
            response = await client.post("/v1/test/reset")
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        # No DB writes: the seeded session still exists.
        assert await _count_sessions(ctx) == 1
        assert any(
            "test_reset_unauthorized: missing_header" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_5_empty_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#5: Authorization: "" → 401 missing_header."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": ""},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: missing_header" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_6_non_bearer_scheme(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#6: Basic auth → 401 wrong_scheme."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": "Basic dGVzdA=="},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: wrong_scheme" in r.message for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


@pytest.mark.parametrize("header_value", ["Bearer ", "Bearer   "])
async def test_scenario_7_bearer_with_no_token(
    header_value: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#7: "Bearer " (no token) or "Bearer    " → 401 empty_token."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": header_value},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: empty_token" in r.message for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_8_wrong_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#8: wrong bearer → 401 token_mismatch; bearer NOT in log text."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": "Bearer wrong-value-do-not-log"},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: token_mismatch" in r.message
            for r in caplog.records
        )
        # Bearer string itself MUST NOT appear anywhere in captured logs.
        assert "wrong-value-do-not-log" not in caplog.text
    finally:
        await ctx.engine.dispose()


async def test_scenario_9_trailing_whitespace_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#9: bearer with trailing whitespace → 401 token_mismatch.

    Trailing whitespace is part of the candidate token. The constant-time
    compare against the raw env value rejects.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            # httpx normalizes single-line header values; embed the trailing
            # space directly.
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN} "},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: token_mismatch" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_10_bearer_with_extra_tokens(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#10: "Bearer foo bar" → 401 token_mismatch (scheme correct, value not)."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": "Bearer foo bar"},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_reset_unauthorized: token_mismatch" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Scenarios 11–14: happy path with various seed states
# ---------------------------------------------------------------------------


async def test_scenario_11_correct_bearer_empty_tables(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#11: empty tables → 204 empty body; counts pre/post both 0.

    Also covers Patch P4 (AC6 load-bearing assertion): the 204 response
    MUST NOT carry a Content-Security-Policy header. CSP is the SPA's
    runtime contract; emitting it on a server-internal e2e endpoint
    would mislead readers about response provenance.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        assert await _count_sessions(ctx) == 0
        assert await _count_auth_states(ctx) == 0
        assert await _count_books(ctx) == 0
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        # Empty body — Starlette/FastAPI omit content-length entirely on
        # 204 responses (per RFC 7230 §3.3.2 — content-length MUST NOT be
        # sent for 1xx/204). The empty-body check is the load-bearing one.
        assert response.content == b""
        # Patch P4: AC6 — no CSP on the 204 path.
        assert "content-security-policy" not in response.headers
        assert await _count_sessions(ctx) == 0
        assert await _count_auth_states(ctx) == 0
        assert await _count_books(ctx) == 0
        assert any(
            "test_reset_truncated" in r.message
            and "sessions_deleted=0" in r.message
            and "auth_states_deleted=0" in r.message
            and "books_deleted=0" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_12_correct_bearer_sessions_populated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#12: 3 sessions seeded → 204; sessions=0 post; log reflects 3 / 0."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        for i in range(3):
            await _seed_session_row(ctx, suffix=f"s12-{i}")
        assert await _count_sessions(ctx) == 3
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        assert await _count_sessions(ctx) == 0
        assert await _count_books(ctx) == 0
        assert any(
            "sessions_deleted=3" in r.message
            and "auth_states_deleted=0" in r.message
            and "books_deleted=0" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_13_correct_bearer_auth_states_populated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#13: 2 auth_states seeded → 204; auth_states=0; log reflects 0 / 2."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        for i in range(2):
            await _seed_auth_state_row(ctx, suffix=f"s13-{i}")
        assert await _count_auth_states(ctx) == 2
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        assert await _count_auth_states(ctx) == 0
        assert await _count_books(ctx) == 0
        assert any(
            "sessions_deleted=0" in r.message
            and "auth_states_deleted=2" in r.message
            and "books_deleted=0" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_14_correct_bearer_both_tables_populated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#14: 5 sessions + 3 auth_states → 204; both 0; log reflects 5 / 3."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        for i in range(5):
            await _seed_session_row(ctx, suffix=f"s14-{i}")
        for i in range(3):
            await _seed_auth_state_row(ctx, suffix=f"s14-{i}")
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        assert await _count_sessions(ctx) == 0
        assert await _count_auth_states(ctx) == 0
        assert await _count_books(ctx) == 0
        assert any(
            "sessions_deleted=5" in r.message
            and "auth_states_deleted=3" in r.message
            and "books_deleted=0" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_14b_correct_bearer_books_populated(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#14b: 4 books seeded → 204; books=0; log reflects 0 / 0 / 4."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        for i in range(4):
            await _seed_book_row(ctx, suffix=f"s14b-{i}")
        assert await _count_books(ctx) == 4
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        assert await _count_books(ctx) == 0
        assert any(
            "sessions_deleted=0" in r.message
            and "auth_states_deleted=0" in r.message
            and "books_deleted=4" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Scenarios 15–16: CSRF exemption and non-regression
# ---------------------------------------------------------------------------


async def test_scenario_15_csrf_exemption_post_without_csrf_material(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#15: POST /v1/test/reset succeeds even with NO csrf cookie/header/origin.

    Demonstrates that `_CSRF_EXEMPT_PATHS` in `bff/auth/csrf.py` correctly
    short-circuits the middleware for this path. The same request shape
    (no CSRF material) would 403 on any other state-changing route — see
    scenario 16.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 204
        # The exemption log line must be present.
        assert any(
            "csrf_exempt_path" in r.message
            and "path=/v1/test/reset" in r.message
            and "method=POST" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_scenario_16_csrf_still_enforced_on_other_state_changing_paths(
    client: AsyncClient,
) -> None:
    """#16: POST /test/open (the stub) without CSRF still 403s.

    Proves the exemption is path-scoped, not a global bypass. Uses the
    bare `client` fixture from conftest (no CSRF cookie / header).
    """
    response = await client.post("/test/open", json={"value": "x"})
    assert response.status_code == 403
    assert response.json() == {
        "errorCode": "csrf_invalid",
        "message": "CSRF token missing or invalid",
        "detail": None,
    }


# ---------------------------------------------------------------------------
# Scenarios 17–19: idempotency + edge cases
# ---------------------------------------------------------------------------


async def test_scenario_17_idempotent_successive_calls(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#17: POST twice in a row → both 204; counts 0 throughout."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        await _seed_session_row(ctx, suffix="s17")
        async with ctx.make_client() as client:
            r1 = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
            r2 = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert r1.status_code == 204
        assert r2.status_code == 204
        assert await _count_sessions(ctx) == 0
        truncated_logs = [
            r for r in caplog.records if "test_reset_truncated" in r.message
        ]
        assert len(truncated_logs) == 2
    finally:
        await ctx.engine.dispose()


async def test_scenario_18_bearer_with_special_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#18: token with special chars (`:`, `@`, etc.) compared as bytes."""
    special_token = "!@#$%^&*():_+abc"
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", special_token)
    ctx = await _build_context(enable=True, token=special_token)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {special_token}"},
            )
        assert response.status_code == 204
    finally:
        await ctx.engine.dispose()


async def test_scenario_19_env_token_with_leading_trailing_whitespace(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#19: env token "  abc  " vs client "Bearer abc" → 401 token_mismatch.

    Spec choice: do NOT silently strip secrets. The env-supplied value is
    compared verbatim. (`.strip()` is only applied at gate-evaluation
    time, not at compare time.)
    """
    spaced_token = "  abc  "
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", spaced_token)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=spaced_token)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": "Bearer abc"},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any("token_mismatch" in r.message for r in caplog.records)
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Scenarios 20–22: OpenAPI + startup-log signaling
# ---------------------------------------------------------------------------


async def test_scenario_20a_openapi_lists_route_when_gate_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#20a: gate ON → `/v1/test/reset` appears in GET /openapi.json."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get("/openapi.json")
        assert response.status_code == 200
        body = response.json()
        assert "/v1/test/reset" in body["paths"]
    finally:
        await ctx.engine.dispose()


async def test_scenario_20b_openapi_omits_route_when_gate_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#20b: gate OFF → `/v1/test/reset` NOT in GET /openapi.json."""
    monkeypatch.setattr(settings, "enable_test_reset", False)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=False, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get("/openapi.json")
        assert response.status_code == 200
        body = response.json()
        assert "/v1/test/reset" not in body["paths"]
    finally:
        await ctx.engine.dispose()


async def test_scenario_21_startup_log_when_gate_on(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#21: gate ON during _build_context → INFO log fires once."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        registered = [
            r for r in caplog.records if "test_reset_route_registered" in r.message
        ]
        assert len(registered) >= 1
    finally:
        await ctx.engine.dispose()


async def test_scenario_22_no_startup_log_when_gate_off(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#22: gate OFF during _build_context → no `test_reset_route_registered`."""
    monkeypatch.setattr(settings, "enable_test_reset", False)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=False, token=_DEFAULT_TOKEN)
    try:
        assert not any(
            "test_reset_route_registered" in r.message for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Scenarios 23+: post-review hardening regressions (Patches P2, P6)
# ---------------------------------------------------------------------------


async def test_scenario_23_trailing_slash_path_is_csrf_exempt_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Patch P2: POST `/v1/test/reset/` (trailing slash) MUST behave like
    the canonical path — bypass CSRF and reach the handler.

    FastAPI's `redirect_slashes=True` 307 still flows through the CSRF
    middleware on the original request URL; without the trailing-slash
    entry in `_CSRF_EXEMPT_PATHS`, the middleware would 403 the request
    BEFORE the slash-redirect could fire. With `follow_redirects=True`,
    httpx follows the 307 and the underlying handler returns 204. The
    load-bearing assertion is `!= 403` — a 204 (route mounted, gate on)
    or even a 404 (gate off, after the redirect) would both be fine; we
    must NOT see the CSRF 403 envelope.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=ctx.app),
            base_url="http://test",
            follow_redirects=True,
        ) as client:
            response = await client.post(
                "/v1/test/reset/",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        # The load-bearing non-regression: NOT a CSRF 403.
        assert response.status_code != 403
        assert response.status_code == 204
        # And the bypass log line for the trailing-slash path must fire.
        assert any(
            "csrf_exempt_path" in r.message and "path=/v1/test/reset/" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


# ---------------------------------------------------------------------------
# Story 1.13: GET /v1/test/session-debug
# ---------------------------------------------------------------------------


async def test_session_debug_route_not_registered_when_gate_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 1.13: gate OFF → GET /v1/test/session-debug returns 404."""
    monkeypatch.setattr(settings, "enable_test_reset", False)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=False, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 404
    finally:
        await ctx.engine.dispose()


async def test_session_debug_missing_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13: no Authorization header → 401 session_expired envelope."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get("/v1/test/session-debug")
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_session_debug_unauthorized: missing_header" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_session_debug_wrong_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13: Bearer mismatch → 401 token_mismatch."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.WARNING, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": "Bearer wrong-token"},
            )
        assert response.status_code == 401
        assert response.json() == _UNAUTHORIZED_BODY
        assert any(
            "test_session_debug_unauthorized: token_mismatch" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_session_debug_no_session_cookie_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13: bearer correct but no bff_session cookie → 404 session_not_found."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 404
        body = response.json()
        assert body["errorCode"] == "session_not_found"
        assert body["detail"] is None
        assert "message" in body
        assert any("test_session_debug_no_cookie" in r.message for r in caplog.records)
    finally:
        await ctx.engine.dispose()


async def test_session_debug_unknown_session_id_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13: bearer correct, cookie does not match any row → 404."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            client.cookies.set("bff_session", "nonexistent-session-id-12345")
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 404
        body = response.json()
        assert body["errorCode"] == "session_not_found"
        assert any(
            "test_session_debug_unknown_session" in r.message for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_session_debug_empty_refresh_token_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13 (review patch): bearer correct, session row exists but
    `refresh_token` is empty → 404 session_not_found.

    `bff.api.auth` stores `str(token.get("refresh_token", ""))` at callback
    time, so a Keycloak response without a refresh_token persists "" into
    the row. Returning 200 with `{"refresh_token": ""}` would silently
    pass the J5 spec's downstream Keycloak POST (empty refresh_token also
    returns invalid_grant) for the wrong reason. Defense-in-depth: treat
    empty refresh_token the same as session_not_found.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)

    session_id = "seeded-session-empty-rt-9999"
    async with ctx.factory() as db:
        db.add(
            entities.Session(
                id=session_id,
                sub="testuser-sub-empty",
                access_token="at",
                refresh_token="",  # empty — the regression case
                id_token="it",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                csrf_secret="cs",
            )
        )
        await db.commit()

    try:
        async with ctx.make_client() as client:
            client.cookies.set("bff_session", session_id)
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 404
        body = response.json()
        assert body["errorCode"] == "session_not_found"
        assert any(
            "test_session_debug_empty_refresh_token" in r.message
            for r in caplog.records
        )
    finally:
        await ctx.engine.dispose()


async def test_session_debug_happy_path_returns_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Story 1.13: bearer correct + valid session → 200 with refresh_token + sub.

    The refresh_token value MUST NOT appear in any captured log line.
    """
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    caplog.set_level(logging.INFO, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)

    refresh_token_value = "rt-secret-do-not-log-abc123"
    session_id = "seeded-session-debug-1234567890"
    sub_value = "testuser-sub-uuid-9876"
    async with ctx.factory() as db:
        db.add(
            entities.Session(
                id=session_id,
                sub=sub_value,
                access_token="at",
                refresh_token=refresh_token_value,
                id_token="it",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                csrf_secret="cs",
            )
        )
        await db.commit()

    try:
        async with ctx.make_client() as client:
            client.cookies.set("bff_session", session_id)
            response = await client.get(
                "/v1/test/session-debug",
                headers={"Authorization": f"Bearer {_DEFAULT_TOKEN}"},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["refresh_token"] == refresh_token_value
        assert body["sub"] == sub_value
        # session_id_safe = first-8-chars + "..." per _safe_session_id_log.
        assert body["session_id_safe"] == f"{session_id[:8]}..."

        # The served-log INFO line was emitted.
        assert any("test_session_debug_served" in r.message for r in caplog.records)
        # The refresh_token value MUST NOT appear in any log line.
        assert refresh_token_value not in caplog.text
        # The full session_id must NOT appear in any log line either.
        assert session_id not in caplog.text
    finally:
        await ctx.engine.dispose()


async def test_session_debug_openapi_lists_route_when_gate_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 1.13: gate ON → `/v1/test/session-debug` appears in OpenAPI."""
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=True, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get("/openapi.json")
        assert response.status_code == 200
        body = response.json()
        assert "/v1/test/session-debug" in body["paths"]
    finally:
        await ctx.engine.dispose()


async def test_session_debug_openapi_omits_route_when_gate_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Story 1.13: gate OFF → `/v1/test/session-debug` NOT in OpenAPI."""
    monkeypatch.setattr(settings, "enable_test_reset", False)
    monkeypatch.setattr(settings, "test_reset_token", _DEFAULT_TOKEN)
    ctx = await _build_context(enable=False, token=_DEFAULT_TOKEN)
    try:
        async with ctx.make_client() as client:
            response = await client.get("/openapi.json")
        assert response.status_code == 200
        body = response.json()
        assert "/v1/test/session-debug" not in body["paths"]
    finally:
        await ctx.engine.dispose()


async def test_scenario_24_db_failure_returns_project_envelope(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Patch P6 / AC10 honest-degradation: a DB error during truncate must
    produce the project's `{errorCode, message, detail}` 500 envelope and
    log a single ERROR line with NO bearer-token material.

    Monkeypatches `AsyncSession.execute` so the first DELETE raises
    `SQLAlchemyError`. The handler is expected to:
      - roll back (best-effort)
      - log `test_reset_db_failure: <ExcType>` at ERROR
      - return 500 with the `INTERNAL_ERROR` envelope
      - emit NO logs containing the bearer token bytes
    """
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession

    bearer = "secret-do-not-log-xyz"
    monkeypatch.setattr(settings, "enable_test_reset", True)
    monkeypatch.setattr(settings, "test_reset_token", bearer)
    caplog.set_level(logging.ERROR, logger="bff.api.test_reset")
    ctx = await _build_context(enable=True, token=bearer)

    original_execute = _AsyncSession.execute

    async def _failing_execute(self, *args, **kwargs):
        raise SQLAlchemyError("simulated db failure")

    monkeypatch.setattr(_AsyncSession, "execute", _failing_execute)
    try:
        async with ctx.make_client() as client:
            response = await client.post(
                "/v1/test/reset",
                headers={"Authorization": f"Bearer {bearer}"},
            )
        assert response.status_code == 500
        body = response.json()
        # Project envelope keys present and correctly populated.
        assert body["errorCode"] == "INTERNAL_ERROR"
        assert "message" in body
        assert "detail" in body
        # Exactly one ERROR line, naming the exception type — not the token.
        failures = [r for r in caplog.records if "test_reset_db_failure" in r.message]
        assert len(failures) == 1
        assert "SQLAlchemyError" in failures[0].getMessage()
        # The bearer token MUST NOT appear anywhere in captured logs.
        assert bearer not in caplog.text
    finally:
        # Restore the patched method before disposing the engine.
        monkeypatch.setattr(_AsyncSession, "execute", original_execute)
        await ctx.engine.dispose()
