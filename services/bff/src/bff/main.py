import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from bff.api.auth import router as auth_router
from bff.api.health import router as health_router
from bff.api.me import router as me_router
from bff.api.test_reset import register_test_reset_router
from bff.api.v1 import router as v1_router
from bff.auth.csrf import CsrfMiddleware
from bff.auth.oidc_discovery import DiscoveryFetchError, fetch_discovery
from bff.core.config import settings
from bff.core.database import dispose_engine
from bff.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from bff.observability.logging import configure_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    configure_logging(settings)
    # Story 7.2: fetch the OIDC discovery doc once at startup and cache on
    # app.state. Fail-fast on any error — operators see the exit code +
    # `discovery_unreachable` log line rather than a runtime 500 on the
    # first /auth/login.
    try:
        app.state.oidc_discovery = await fetch_discovery(
            settings.effective_oidc_discovery_url,
            expected_issuer=settings.oidc_issuer_url,
            connect_timeout=settings.oidc_discovery_connect_timeout,
            read_timeout=settings.oidc_discovery_read_timeout,
        )
    except DiscoveryFetchError as exc:
        logger.error("discovery_unreachable: %s", exc.classifier)
        raise
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

# Story 6.4 / Epic 6 close: CSP attachment middleware was removed from the
# BFF (CSP source moved to the SPA SSR edge per architecture A8 amendment —
# see `spa/src/server/csp.middleware.ts`). The BFF is API-only post-6.3 and
# never produces HTML responses, so no CSP attachment is needed here.
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
