"""Route-level tests for POST /v1/test/reset (Story 3.4).

Covers gating (env on/off + empty / whitespace / placeholder token rejection),
bearer auth (every malformed-header classifier), truncation of
``reading_speeds``, JWT-non-interaction, OpenAPI surface, and commit-failure
behavior. Doubled ``test_`` prefix in the filename is intentional — the RS
route module is ``api/test_reset.py``; pytest discovers this file via the
``test_*.py`` convention.

The per-test fixture pattern (``_build_test_context``) builds a fresh
``FastAPI`` app + in-memory SQLite engine per scenario so gate state can
vary cleanly without un-registering routes from the global ``app``
singleton imported by ``tests/conftest.py``.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from resource_server.api.test_reset import (
    _settings_dep,
    register_test_reset_router,
)
from resource_server.core.config import AppSettings
from resource_server.core.config import settings as module_settings
from resource_server.core.database import get_session
from resource_server.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from resource_server.models.entities.reading_speed import ReadingSpeed

_TEST_RESET_LOGGER: Final[str] = "resource_server.api.test_reset"
_OIDC_BEARER_LOGGER: Final[str] = "resource_server.auth.oidc_bearer"

_OIDC_STUBS: Final[dict[str, str]] = {
    "oidc_issuer_url": "http://keycloak-test/realms/test",
    "oidc_jwks_url": "http://keycloak-test/realms/test/protocol/openid-connect/certs",
    "oidc_audience": "bmad-books-resource-server",
}


@dataclass
class _TestContext:
    """Per-scenario harness: fresh app + engine + sessionmaker."""

    app: FastAPI
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    settings: AppSettings


async def _build_test_context(*, enable: bool, token: str) -> _TestContext:
    """Build a fresh app + engine bound together via dependency override.

    The fresh ``AppSettings`` includes non-empty OIDC stubs because Story
    3.1 added required-fail-fast validators (``core/config.py:114-139``);
    the same placeholder values used by ``tests/conftest.py`` (lines
    20-25) satisfy the validator without leaking real values into
    pytest output.
    """
    cfg = AppSettings(
        enable_test_reset=enable,
        test_reset_token=token,
        **_OIDC_STUBS,  # type: ignore[arg-type]
    )

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    sessionmaker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    app = FastAPI()
    # Mirror main.py:65-66 so the response envelopes match production for
    # any AppException / RequestValidationError surface tests might trip.
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    async def _override_session() -> AsyncGenerator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    def _override_settings() -> AppSettings:
        return cfg

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[_settings_dep] = _override_settings

    register_test_reset_router(app, cfg)
    return _TestContext(app=app, engine=engine, sessionmaker=sessionmaker, settings=cfg)


@asynccontextmanager
async def _client_for(ctx: _TestContext) -> AsyncGenerator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=ctx.app), base_url="http://test"
    ) as c:
        yield c


async def _row_count(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        result = await session.execute(select(func.count()).select_from(ReadingSpeed))
        return int(result.scalar_one())


async def _seed_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    rows: list[ReadingSpeed],
) -> None:
    async with sessionmaker() as session:
        session.add_all(rows)
        await session.commit()


# ---------------------------------------------------------------------------
# Scenarios 1-4: route not registered when gate is off OR token misconfigured.
# ---------------------------------------------------------------------------


async def test_scenario_01_gate_off_route_not_registered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=False, token="secret-xyz")
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    # Clean gate-off: NO skip-warn log emitted (the helper returns
    # immediately after the enable-flag check).
    assert "test_reset_route_skipped" not in caplog.text
    # Other methods also return 404.
    async with _client_for(ctx) as c:
        for method in ("GET", "PUT", "DELETE", "PATCH"):
            r = await c.request(method, "/v1/test/reset")
            assert r.status_code == 404, f"{method} should 404"


async def test_scenario_02_gate_on_empty_token_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="")
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}
    assert "test_reset_route_skipped reason=test_reset_token_empty" in caplog.text


async def test_scenario_03_gate_on_whitespace_token_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="   ")
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 404
    # Empty-after-strip uses the SAME classifier as truly-empty.
    assert "test_reset_route_skipped reason=test_reset_token_empty" in caplog.text


async def test_scenario_04_gate_on_placeholder_token_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RS-specific defensive check (the BFF Story 1.12 does NOT have this)."""
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="change-me")
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 404
    assert (
        "test_reset_route_skipped reason=test_reset_token_default_placeholder"
        in caplog.text
    )


# CR3 patches: normalized placeholder reject also catches typo variants.


@pytest.mark.parametrize(
    "variant",
    [
        "Change-Me",
        "CHANGE-ME",
        "change_me",
        "Change_Me",
        "CHANGE_ME",
        "changeme",
        "ChangeMe",
        "CHANGEME",
        "  change-me  ",
        "  CHANGE-ME  ",
    ],
)
async def test_cr3_placeholder_variants_rejected(
    caplog: pytest.LogCaptureFixture, variant: str
) -> None:
    """Case + underscore-normalized placeholder reject catches typo variants.

    The dev log's reject was originally case-sensitive on the literal
    ``"change-me"``; CR3 expanded it to normalize ``.lower()`` and
    ``_``→``-`` so trivial operator typos still trip the gate.
    """
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token=variant)
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 404, f"variant {variant!r} bypassed gate"
    assert (
        "test_reset_route_skipped reason=test_reset_token_default_placeholder"
        in caplog.text
    )


# CR1 patch: startup WARN when token has surrounding whitespace.


async def test_cr1_startup_warn_when_token_whitespace_padded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Operator sets ``TEST_RESET_TOKEN="\\nsecret\\n"`` (accidental newline).

    The gate uses the stripped form (passes), but the handler runtime
    compare uses the raw value — so any legitimate ``Bearer secret`` call
    would silently 401. The fix logs a WARN at registration time so the
    misconfig surfaces in boot logs.
    """
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    # Use a token where strip() yields a non-placeholder, non-empty value.
    raw = "  secret-xyz  "
    ctx = await _build_test_context(enable=True, token=raw)
    # The route IS mounted (gate passed) — verify by hitting it with the
    # RAW token (with whitespace) and confirming the comparison succeeds.
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": f"Bearer {raw}"}
        )
    assert response.status_code == 204
    # AND the WARN about whitespace padding is captured at startup.
    assert "test_reset_token_whitespace_padded" in caplog.text
    assert "raw_token_len=14" in caplog.text  # "  secret-xyz  " = 14 chars
    assert "stripped_token_len=10" in caplog.text  # "secret-xyz" = 10 chars


async def test_cr1_no_warn_when_token_already_stripped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No false-positive WARN when the env token has no surrounding whitespace."""
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    await _build_test_context(enable=True, token="secret-xyz")
    assert "test_reset_token_whitespace_padded" not in caplog.text


# CR2 patch: OpenAPI schema declares both 204 and 401.


async def test_cr2_openapi_declares_401_response() -> None:
    """The route documents both the 204 happy path and the 401 envelope."""
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    async with _client_for(ctx) as c:
        response = await c.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    responses = body["paths"]["/v1/test/reset"]["post"]["responses"]
    assert "204" in responses
    assert "401" in responses
    # 401 carries the canonical envelope example. (Note: FastAPI's OpenAPI
    # JSON serialization drops keys with ``None`` values, so ``detail`` —
    # which the handler returns as null — is omitted from the example dict
    # here even though the runtime envelope DOES contain ``"detail": null``.)
    example = responses["401"]["content"]["application/json"]["example"]
    assert example["errorCode"] == "session_expired"
    assert example["message"] == "Authentication required"


# ---------------------------------------------------------------------------
# Scenarios 5-12: bearer-auth failure modes (all 401, no DB writes, no logged
# bearer material).
# ---------------------------------------------------------------------------


_EXPECTED_401_BODY: Final[dict[str, object]] = {
    "errorCode": "session_expired",
    "message": "Authentication required",
    "detail": None,
}


async def _assert_401_no_writes(
    response_body: dict[str, object],
    sessionmaker: async_sessionmaker[AsyncSession],
    pre_count: int,
) -> None:
    assert response_body == _EXPECTED_401_BODY
    assert await _row_count(sessionmaker) == pre_count


async def test_scenario_05_missing_authorization_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset")
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: missing_header" in caplog.text


async def test_scenario_06_empty_authorization_header(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post("/v1/test/reset", headers={"Authorization": ""})
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    # An empty-string header is classified the same as an absent one.
    assert "test_reset_unauthorized: missing_header" in caplog.text


async def test_scenario_07_basic_scheme_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Basic dGVzdA=="}
        )
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: wrong_scheme" in caplog.text


async def test_scenario_08_jwt_scheme_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pin JWT-scheme rejection — other RS endpoints DO accept Bearer JWTs."""
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "JWT abc.def.ghi"}
        )
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: wrong_scheme" in caplog.text


async def test_scenario_09_bearer_with_no_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    for value in ("Bearer ", "Bearer    "):
        async with _client_for(ctx) as c:
            response = await c.post("/v1/test/reset", headers={"Authorization": value})
        assert response.status_code == 401, f"failed for header={value!r}"
        await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: empty_token" in caplog.text


async def test_scenario_10_bearer_with_wrong_token(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer wrong-value"}
        )
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: token_mismatch" in caplog.text
    # The bearer string MUST NOT appear anywhere in captured logs.
    assert "wrong-value" not in caplog.text


async def test_scenario_11_bearer_with_trailing_whitespace_rejected(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset",
            headers={"Authorization": "Bearer secret-xyz "},
        )
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    # Trailing whitespace is part of the bearer token by spec; constant-time
    # compare against the raw env value rejects.
    assert "test_reset_unauthorized: token_mismatch" in caplog.text


async def test_scenario_12_bearer_with_extra_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """``Bearer foo bar`` classifies as ``token_mismatch``, not ``wrong_scheme``."""
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    pre = await _row_count(ctx.sessionmaker)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer foo bar"}
        )
    assert response.status_code == 401
    await _assert_401_no_writes(response.json(), ctx.sessionmaker, pre)
    assert "test_reset_unauthorized: token_mismatch" in caplog.text
    assert "test_reset_unauthorized: wrong_scheme" not in caplog.text


# ---------------------------------------------------------------------------
# Scenarios 13-15: happy path + row-count assertions.
# ---------------------------------------------------------------------------


async def test_scenario_13_happy_path_empty_table(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    assert await _row_count(ctx.sessionmaker) == 0
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
    assert response.status_code == 204
    # 204 No Content: per RFC 7230 §3.3.2 a Content-Length header is optional
    # for responses that MUST NOT have a body. FastAPI's bare ``Response``
    # omits the header; the body itself is the load-bearing guarantee.
    assert response.content == b""
    assert await _row_count(ctx.sessionmaker) == 0
    assert (
        "test_reset_truncated tables=reading_speeds reading_speeds_deleted=0"
        in caplog.text
    )


async def test_scenario_14_happy_path_one_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(ctx.sessionmaker, [ReadingSpeed(sub="user-a", pages_per_hour=30)])
    assert await _row_count(ctx.sessionmaker) == 1
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
    assert response.status_code == 204
    assert await _row_count(ctx.sessionmaker) == 0
    assert (
        "test_reset_truncated tables=reading_speeds reading_speeds_deleted=1"
        in caplog.text
    )


async def test_scenario_15_happy_path_five_rows(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(
        ctx.sessionmaker,
        [ReadingSpeed(sub=f"user-{i}", pages_per_hour=30 + i) for i in range(5)],
    )
    assert await _row_count(ctx.sessionmaker) == 5
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
    assert response.status_code == 204
    assert await _row_count(ctx.sessionmaker) == 0
    assert (
        "test_reset_truncated tables=reading_speeds reading_speeds_deleted=5"
        in caplog.text
    )


# ---------------------------------------------------------------------------
# Scenario 16: JWT material is ignored on this route.
# ---------------------------------------------------------------------------


async def test_scenario_16_jwt_material_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(ctx.sessionmaker, [ReadingSpeed(sub="user-a", pages_per_hour=30)])
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset",
            headers={
                "Authorization": "Bearer secret-xyz",
                "X-User": "attacker",
                "X-Forwarded-Token": (
                    "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhdHRhY2tlciJ9.invalid"
                ),
            },
        )
    assert response.status_code == 204
    assert await _row_count(ctx.sessionmaker) == 0
    # The JWT path never ran — no log from the oidc_bearer logger.
    oidc_records = [r for r in caplog.records if r.name == _OIDC_BEARER_LOGGER]
    assert oidc_records == [], f"unexpected JWT logs: {oidc_records!r}"
    assert "test_reset_truncated" in caplog.text


# ---------------------------------------------------------------------------
# Scenario 17: idempotent successive calls.
# ---------------------------------------------------------------------------


async def test_scenario_17_idempotent_successive_calls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(
        ctx.sessionmaker,
        [ReadingSpeed(sub=f"user-{i}", pages_per_hour=30) for i in range(3)],
    )
    async with _client_for(ctx) as c:
        r1 = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
        r2 = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
    assert r1.status_code == 204
    assert r2.status_code == 204
    assert await _row_count(ctx.sessionmaker) == 0
    info_logs = [
        rec.getMessage()
        for rec in caplog.records
        if rec.name == _TEST_RESET_LOGGER and rec.levelno == logging.INFO
    ]
    truncated_logs = [m for m in info_logs if "test_reset_truncated" in m]
    assert len(truncated_logs) == 2
    assert "reading_speeds_deleted=3" in truncated_logs[0]
    assert "reading_speeds_deleted=0" in truncated_logs[1]


# ---------------------------------------------------------------------------
# Scenarios 18-19: edge-case bearer tokens.
# ---------------------------------------------------------------------------


async def test_scenario_18_special_chars_bearer_token() -> None:
    token = "!@#$%^&*():_+"
    ctx = await _build_test_context(enable=True, token=token)
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 204


async def test_scenario_19_env_token_whitespace_not_silently_stripped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Env value is compared verbatim; secrets are not silently trimmed."""
    caplog.set_level(logging.WARNING, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="  abc  ")
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer abc"}
        )
    assert response.status_code == 401
    assert response.json() == _EXPECTED_401_BODY
    assert "test_reset_unauthorized: token_mismatch" in caplog.text


# ---------------------------------------------------------------------------
# Scenarios 20-21: OpenAPI surface reflects the gate.
# ---------------------------------------------------------------------------


async def test_scenario_20_openapi_includes_route_when_gate_on() -> None:
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    async with _client_for(ctx) as c:
        response = await c.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert "/v1/test/reset" in body["paths"]
    assert body["paths"]["/v1/test/reset"]["post"]["tags"] == ["Test Reset"]


async def test_scenario_21_openapi_omits_route_when_gate_off() -> None:
    ctx = await _build_test_context(enable=False, token="secret-xyz")
    async with _client_for(ctx) as c:
        response = await c.get("/openapi.json")
    assert response.status_code == 200
    body = response.json()
    assert "/v1/test/reset" not in body["paths"]


# ---------------------------------------------------------------------------
# Scenarios 22-23: startup logs reflect the gate.
# ---------------------------------------------------------------------------


async def test_scenario_22_startup_info_log_when_gate_on(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    await _build_test_context(enable=True, token="secret-xyz")
    assert "test_reset_route_registered path=/v1/test/reset" in caplog.text


async def test_scenario_23_no_startup_info_log_when_gate_off(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    await _build_test_context(enable=False, token="secret-xyz")
    assert "test_reset_route_registered" not in caplog.text


# ---------------------------------------------------------------------------
# Scenario 24: commit failure surfaces as an error; rows are not lost.
# ---------------------------------------------------------------------------


async def test_scenario_24_commit_failure_surfaces_500_no_data_loss(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A DB-side failure during commit must NOT be swallowed; data preserved."""
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(ctx.sessionmaker, [ReadingSpeed(sub="user-a", pages_per_hour=30)])

    # Inject a session whose commit() raises. Override get_session AFTER
    # register_test_reset_router has run so the route is mounted, but the
    # handler-level dependency resolves to our faulty wrapper. The wrapper
    # delegates EVERY attribute access (including ``execute``) to the real
    # session via ``__getattr__`` and only overrides ``commit`` — keeping
    # the dynamic-attribute proxy fully type-checker-friendly (no overload
    # mismatch against SQLAlchemy's ``AsyncSession.execute`` signature).
    class _FaultyCommitSession:
        def __init__(self, real: AsyncSession) -> None:
            self._real = real

        async def commit(self) -> None:
            raise RuntimeError("simulated DB disconnect")

        def __getattr__(self, name: str) -> object:
            return getattr(self._real, name)

    async def _faulty_override() -> AsyncGenerator[object]:
        async with ctx.sessionmaker() as real:
            yield _FaultyCommitSession(real)

    ctx.app.dependency_overrides[get_session] = _faulty_override

    response = None
    async with _client_for(ctx) as c:
        # FastAPI's default behavior with no Exception handler is to
        # propagate the exception out through the ASGI transport. The
        # critical guarantee being pinned here is "the handler did NOT
        # swallow it" — i.e., no 204.
        with contextlib.suppress(RuntimeError):
            response = await c.post(
                "/v1/test/reset",
                headers={"Authorization": "Bearer secret-xyz"},
            )

    # Either path satisfies the no-swallow guarantee: an explicit 500
    # response OR an exception that bubbled out of the ASGI stack.
    if response is not None:
        assert response.status_code >= 500, (
            f"handler must not silently succeed on commit failure; "
            f"got {response.status_code}"
        )

    # Data is preserved (no truncate-then-fail data loss).
    assert await _row_count(ctx.sessionmaker) == 1


# ---------------------------------------------------------------------------
# Scenario 25: truncate is intentionally global, not sub-scoped.
# ---------------------------------------------------------------------------


def test_settings_dep_returns_module_settings() -> None:
    """Direct coverage of the dependency factory.

    Every other test overrides ``_settings_dep`` via
    ``app.dependency_overrides`` so the production-path ``return settings``
    branch is otherwise unexercised. This pins it to the actual module-level
    singleton.
    """
    assert _settings_dep() is module_settings


async def test_scenario_25_truncate_is_global_not_per_user(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Truncate removes ALL users' rows — this is the e2e clean-slate primitive.

    Differs from /v1/reading-speed GET/PUT which are sub-scoped to the
    JWT principal. The test-reset endpoint is a maintenance lever, not
    a per-user clear.
    """
    caplog.set_level(logging.INFO, logger=_TEST_RESET_LOGGER)
    ctx = await _build_test_context(enable=True, token="secret-xyz")
    await _seed_rows(
        ctx.sessionmaker,
        [
            ReadingSpeed(sub="user-a", pages_per_hour=30),
            ReadingSpeed(sub="user-b", pages_per_hour=40),
            ReadingSpeed(sub="user-c", pages_per_hour=50),
        ],
    )
    assert await _row_count(ctx.sessionmaker) == 3
    async with _client_for(ctx) as c:
        response = await c.post(
            "/v1/test/reset", headers={"Authorization": "Bearer secret-xyz"}
        )
    assert response.status_code == 204
    assert await _row_count(ctx.sessionmaker) == 0
