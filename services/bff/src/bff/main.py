from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import FileResponse, Response
from starlette.staticfiles import StaticFiles

from bff.api.auth import router as auth_router
from bff.api.health import router as health_router
from bff.api.me import router as me_router
from bff.api.test_reset import register_test_reset_router
from bff.api.v1 import router as v1_router
from bff.auth.csrf import CsrfMiddleware
from bff.core.config import settings
from bff.core.database import dispose_engine
from bff.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from bff.middleware.security_headers import SecurityHeadersMiddleware
from bff.observability.logging import configure_logging

# Default SPA static directory — populated by the multi-stage Dockerfile
# (Story 1.14 / AR24). In dev runs (plain `uv run uvicorn`) this path does
# not exist and the SPA mount is skipped (see `_register_spa` guard).
_SPA_DIR = Path("/app/static")


def _register_spa(application: FastAPI, static_dir: Path) -> None:
    """Conditionally mount the Angular SPA bundle on `application`.

    Called at startup with `_SPA_DIR` (production) or with a `tmp_path`
    fixture-supplied directory (tests — AC7). Factored into a helper so
    that tests can call it directly after constructing a fresh app instance
    without coupling to module-load-time side effects.

    Mount order (AC3, AC4):
    1. /assets  — StaticFiles without html fallback (real asset files only).
       Registered first so /assets/* hits the StaticFiles handler.
    2. /{full_path:path}  — FastAPI catch-all: serves index.html for HTML
       clients, returns the 404 JSON envelope (D16) for non-HTML clients.

    Starlette matches routes in declaration order: the /assets mount is added
    BEFORE the catch-all so /assets/* requests are served by StaticFiles, and
    everything else falls through to the catch-all. For requests to known
    paths that exist as files, FileResponse is returned directly; for unknown
    paths, the Accept header determines whether to serve index.html or the
    404 envelope.
    """
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        application.mount(
            "/assets",
            StaticFiles(directory=str(assets_dir)),
            name="spa-assets",
        )

    static_root = static_dir.resolve()

    @application.api_route(
        "/{full_path:path}",
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )
    async def _spa_or_404(request: Request, full_path: str) -> Response:
        # Try to resolve as a real file first (e.g. favicon.ico, main.js, etc.)
        # Resolve the candidate path and verify it stays within static_root so
        # a crafted `..`-laden URL cannot escape the bundle directory.
        try:
            candidate = (static_dir / full_path).resolve()
            candidate.relative_to(static_root)
            is_file = candidate.is_file()
        except OSError, ValueError:
            is_file = False
            candidate = static_root
        if is_file:
            return FileResponse(str(candidate))
        # Not a real file — check whether the client accepts HTML.
        accept = request.headers.get("accept", "")
        if "text/html" in accept or "*/*" in accept or accept == "":
            # Browser navigation: serve the Angular shell (history-API fallback).
            return FileResponse(str(static_dir / "index.html"))
        # Non-HTML client (e.g. curl with Accept: application/json) hitting an
        # unknown path → project 404 envelope (D16, AC4).
        return JSONResponse(
            {"errorCode": "not_found", "message": "Not found", "detail": None},
            status_code=404,
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    configure_logging(settings)
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(
    title="bff",
    description="BMAD_books Backend-for-Frontend (OAuth client, books domain).",
    root_path=settings.root_path,
    lifespan=lifespan,
)

if settings.cors_enabled:
    app.add_middleware(
        CORSMiddleware,  # ty: ignore[invalid-argument-type] -- starlette's add_middleware signature uses *args/**kwargs, not typed per-middleware
        allow_origins=settings.cors_allow_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods_list,
        allow_headers=settings.cors_allow_headers_list,
        expose_headers=settings.cors_expose_headers_list,
    )

# Starlette middleware stack is LIFO: the last `add_middleware` is the
# OUTERMOST in the onion (it wraps the inner ones) and runs first on the
# way in. CsrfMiddleware is added last so it sits outside SecurityHeaders,
# meaning a CSRF-403 short-circuit returns before SecurityHeaders is
# entered and never receives the rejection response (the 403 is JSON, not
# HTML, so no CSP needed). See Story 1.6 Dev Notes "Middleware ordering"
# for the full onion diagram.
app.add_middleware(SecurityHeadersMiddleware)  # ty: ignore[invalid-argument-type] -- starlette's add_middleware signature uses *args/**kwargs, not typed per-middleware
app.add_middleware(CsrfMiddleware)  # ty: ignore[invalid-argument-type] -- starlette's add_middleware signature uses *args/**kwargs, not typed per-middleware

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(health_router)
app.include_router(me_router)
app.include_router(auth_router)
app.include_router(v1_router)
# Story 1.12: conditionally mount POST /v1/test/reset when
# ENABLE_TEST_RESET=true AND TEST_RESET_TOKEN is set. In production
# (default compose profile) this is a no-op; the e2e profile flips the
# gate via compose/app.e2e.yml.
register_test_reset_router(app, settings)

# Story 1.14 (AR24): conditionally mount the Angular SPA bundle.
# The guard means `uv run uvicorn bff.main:app` (dev mode, no built bundle)
# starts cleanly without /app/static. In the compose-built image, /app/static
# is always present (copied from the node-builder stage in the Dockerfile).
if _SPA_DIR.is_dir():
    _register_spa(app, _SPA_DIR)
