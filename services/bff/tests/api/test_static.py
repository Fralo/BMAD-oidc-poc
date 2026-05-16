"""Tests for Story 1.14: BFF serves the Angular SPA bundle (AR24).

Three test cases per AC7:

AC7a — GET /login returns the SPA shell (text/html, contains <app-root>).
AC7b — GET /assets/main.css returns CSS with status 200 and text/css content-type.
AC7c — GET /nonexistent.json with Accept: application/json returns the 404 envelope
        and does NOT serve index.html.

The tests build an isolated FastAPI app using `_register_spa` (the same helper
called in main.py at startup) so they are independent of the module-load-time
`_SPA_DIR.is_dir()` guard and do not interfere with the shared `app` fixture
used by other test modules.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

from bff.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from bff.main import _register_spa

# ---------------------------------------------------------------------------
# Fixture: minimal SPA directory + isolated app
# ---------------------------------------------------------------------------


@pytest.fixture(name="spa_app")
def spa_app_fixture(tmp_path: Path) -> FastAPI:
    """Build a minimal SPA static directory and a fresh FastAPI app with the
    SPA routes registered against it.

    Directory layout:
        tmp_path/
          index.html          — Angular shell with <app-root>
          assets/
            main.css          — minimal CSS file (AC7b)
    """
    # Create the minimal SPA bundle that mirrors what `ng build` outputs.
    index = tmp_path / "index.html"
    index.write_text("<html><body><app-root></app-root></body></html>")

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "main.css").write_text("body { margin: 0; }")

    # Build an isolated app with error handlers (so the 404 envelope is
    # rendered correctly) and mount the SPA routes.
    application = FastAPI(title="bff-spa-test", lifespan=None)
    application.add_exception_handler(AppException, app_exception_handler)
    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    _register_spa(application, tmp_path)
    return application


# ---------------------------------------------------------------------------
# AC7a — GET /login returns SPA shell
# ---------------------------------------------------------------------------


async def test_get_login_returns_spa_shell(spa_app: FastAPI) -> None:
    """AC7a: a browser navigating to /login receives the Angular index.html."""
    async with AsyncClient(
        transport=ASGITransport(app=spa_app),
        base_url="http://test",
        headers={"Accept": "text/html,application/xhtml+xml,*/*"},
    ) as client:
        response = await client.get("/login")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<app-root>" in response.text


# ---------------------------------------------------------------------------
# AC7b — GET /assets/main.css returns CSS with correct content-type
# ---------------------------------------------------------------------------


async def test_get_css_asset_returns_200_with_text_css(spa_app: FastAPI) -> None:
    """AC7b: a request to /assets/main.css returns 200 with text/css content-type."""
    async with AsyncClient(
        transport=ASGITransport(app=spa_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/assets/main.css")

    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# AC7c — GET /nonexistent.json with Accept: application/json → 404 envelope
# ---------------------------------------------------------------------------


async def test_get_unknown_path_with_json_accept_returns_404_envelope(
    spa_app: FastAPI,
) -> None:
    """AC7c: a non-HTML client hitting an unknown path gets the 404 JSON
    envelope and NOT the Angular index.html."""
    async with AsyncClient(
        transport=ASGITransport(app=spa_app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/nonexistent.json",
            headers={"Accept": "application/json"},
        )

    assert response.status_code == 404
    body = response.json()
    assert body["errorCode"] == "not_found"
    assert body["message"] == "Not found"
    assert body["detail"] is None
    # The response body must NOT be the SPA shell.
    assert "<app-root>" not in response.text


# ---------------------------------------------------------------------------
# Path-traversal defence — a crafted `..` URL must not escape static_dir
# ---------------------------------------------------------------------------


async def test_path_traversal_does_not_escape_static_dir(spa_app: FastAPI) -> None:
    """The catch-all resolves `static_dir / full_path` and must stay inside
    `static_dir`. A URL like `/../../../etc/passwd` must NOT serve the real
    /etc/passwd; instead it falls through to the SPA shell (HTML accept) or
    the 404 envelope (JSON accept)."""
    async with AsyncClient(
        transport=ASGITransport(app=spa_app),
        base_url="http://test",
        headers={"Accept": "application/json"},
    ) as client:
        response = await client.get("/../../../etc/passwd")

    # The escape attempt is not served as a file — must hit the 404 envelope
    # (because the Accept header is JSON, the unknown-path branch fires).
    assert response.status_code == 404
    body = response.json()
    assert body["errorCode"] == "not_found"
    # And definitely not the contents of a real system file.
    assert "root:" not in response.text
