import importlib
from collections.abc import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import resource_server.core.config as core_config_module
import resource_server.main as main_module


def _reload_main_app() -> FastAPI:
    # Only reload main_module; core_config_module is NOT reloaded so that the
    # settings singleton object remains the same instance referenced by all
    # imported modules. CORS middleware wiring happens at module level based on
    # settings.cors_enabled, which callers must patch before calling this function.
    module = importlib.reload(main_module)
    return module.app


@pytest.fixture(autouse=True)
def _restore_main_module() -> Generator[None]:
    # monkeypatch (which restores patched attributes) is finalized before this
    # autouse fixture's teardown, so settings are already restored when we reload.
    yield
    _reload_main_app()


def _patch_health_probes_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    """Story 3.1: /health now runs three real probes (DB / Alembic / JWKS).

    The CORS tests use /health as a generic GET endpoint to verify
    middleware-emitted headers, not /health's contract — so we stub all
    three probes to succeed and isolate the test to its actual concern.
    """
    from resource_server.api import health as health_module

    monkeypatch.setattr(
        health_module, "_check_database", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        health_module, "_check_alembic_at_head", AsyncMock(return_value=(True, ""))
    )
    monkeypatch.setattr(
        health_module, "_check_jwks", AsyncMock(return_value=(True, ""))
    )


async def test_cors_disabled_by_default_omits_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_health_probes_ok(monkeypatch)
    app = _reload_main_app()

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        # Re-apply the patch after reload (importlib.reload reinstates the
        # original module references against which monkeypatch patched).
        _patch_health_probes_ok(monkeypatch)
        response = await client.get(
            "/health", headers={"Origin": "http://frontend.example"}
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_cors_enabled_returns_preflight_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core_config_module.settings, "cors_enabled", True)
    monkeypatch.setattr(
        core_config_module.settings,
        "cors_allow_origins",
        "http://frontend.example",
    )
    monkeypatch.setattr(
        core_config_module.settings,
        "cors_allow_methods",
        "GET,POST,OPTIONS",
    )
    monkeypatch.setattr(
        core_config_module.settings,
        "cors_allow_headers",
        "Authorization,Content-Type",
    )
    app = _reload_main_app()

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.options(
            "/health",
            headers={
                "Origin": "http://frontend.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == (
        "http://frontend.example"
    )
