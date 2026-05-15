from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from bff.api.auth import router as auth_router
from bff.api.health import router as health_router
from bff.api.me import router as me_router
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
# innermost (runs first on the way in). SecurityHeaders sits INSIDE Csrf so
# that a CSRF-403 short-circuit bypasses CSP attachment (the 403 is JSON,
# not HTML). See Story 1.6 Dev Notes "Middleware ordering" for the full
# onion diagram.
app.add_middleware(SecurityHeadersMiddleware)  # ty: ignore[invalid-argument-type] -- starlette's add_middleware signature uses *args/**kwargs, not typed per-middleware
app.add_middleware(CsrfMiddleware)  # ty: ignore[invalid-argument-type] -- starlette's add_middleware signature uses *args/**kwargs, not typed per-middleware

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(health_router)
app.include_router(me_router)
app.include_router(auth_router)
app.include_router(v1_router)
