from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel

from resource_server.api.health import router as health_router
from resource_server.api.test_reset import register_test_reset_router
from resource_server.api.v1 import router as v1_router
from resource_server.api.v2 import router as v2_router
from resource_server.core.config import settings
from resource_server.core.database import (
    dispose_engine,
    get_engine,
    is_local_dev_mode,
)
from resource_server.core.errors import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from resource_server.models import (
    entities,  # noqa: F401 -- ensure SQLModel metadata sees all entity definitions
)
from resource_server.observability.logging import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    # Story 3.1: observability stack is intentionally inert (no OTEL exporter
    # wiring, no /metrics endpoint) per the 2026-05-14 sprint-change cut +
    # AR1 archetype-mandate note. The archetype's observability/* helpers
    # exist in the source tree but are not invoked. Story 3.1 ships zero
    # SQLModel entities, so the SQLite `create_all` is a no-op until Story
    # 3.3 lands the first ReadingSpeed entity.
    configure_logging(settings)
    engine = get_engine(settings)
    if is_local_dev_mode(settings):
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(
    title="resource-server",
    description="BMAD_books Resource Server (reading speed, estimate).",
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

app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.include_router(health_router)
app.include_router(v1_router)
app.include_router(v2_router)
register_test_reset_router(app, settings)
