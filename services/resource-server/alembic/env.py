"""Alembic environment for the Resource Server.

Resolves the database URL from the RS's pydantic-settings config
(`AppSettings.effective_database_url` — which prefers `RS_DATABASE_URL`
over the archetype's `DATABASE_URL` and falls back to in-memory SQLite),
then runs migrations via SQLAlchemy's async engine.

Target metadata is `SQLModel.metadata` so SQLModel-declared entities
participate in `--autogenerate`. Story 3.1 ships zero entities; Story 3.3
introduces ReadingSpeed.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from resource_server.core.config import settings
from resource_server.core.database import _to_async_url
from resource_server.models import (
    entities,  # noqa: F401 -- ensure SQLModel metadata sees all entity definitions
)

# Alembic Config object — provides access to .ini values.
config = context.config

# Configure Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the runtime database URL from RS settings, normalizing to the
# async dialect (sqlite+aiosqlite, mysql+aiomysql) the app uses at runtime.
_resolved_url = _to_async_url(settings.effective_database_url)
config.set_main_option("sqlalchemy.url", _resolved_url)

# SQLModel.metadata aggregates every imported entity. The
# `from resource_server.models import entities` above triggers registration;
# Story 3.3 onwards adds real SQLModels under
# `resource_server.models.entities.*`.
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emits SQL without a DBAPI)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations against it."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
