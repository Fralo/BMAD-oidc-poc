from collections.abc import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from bff.core.config import AppSettings
from bff.core.config import settings as _default_settings

_engine: AsyncEngine | None = None

SQLITE_PREFIX = "sqlite"
SQLITE_ASYNC_URL = "sqlite+aiosqlite://"


def _to_async_url(url: str) -> str:
    """Rewrite a sync dialect URL to its async equivalent when needed."""
    parsed = make_url(url)
    backend = parsed.get_backend_name()
    if backend == "sqlite" and "+aiosqlite" not in parsed.drivername:
        return str(parsed.set(drivername="sqlite+aiosqlite"))
    if backend == "mysql" and "+aiomysql" not in parsed.drivername:
        return str(parsed.set(drivername="mysql+aiomysql"))
    return str(parsed)


def create_sqlite_engine(
    url: str = SQLITE_ASYNC_URL,
    *,
    echo: bool = False,
) -> AsyncEngine:
    """Create an async engine for SQLite (StaticPool, check_same_thread=False)."""
    return create_async_engine(
        url,
        echo=echo,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def create_url_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Create an async engine from a given URL for non-SQLite backends."""
    return create_async_engine(url, echo=echo)


def is_local_dev_mode(settings: AppSettings | None = None) -> bool:
    """True when DB is SQLite (local/dev); table creation allowed."""
    cfg = settings if settings is not None else _default_settings
    backend = make_url(cfg.effective_database_url).get_backend_name()
    return backend == SQLITE_PREFIX


def get_engine(settings: AppSettings | None = None) -> AsyncEngine:
    global _engine  # noqa: PLW0603
    if _engine is None:
        cfg = settings if settings is not None else _default_settings
        effective = cfg.effective_database_url
        try:
            async_url = _to_async_url(effective)
        except Exception as e:
            raise ValueError(f"Invalid DATABASE_URL: {effective!r}. {e!s}") from e
        if make_url(async_url).get_backend_name() == SQLITE_PREFIX:
            _engine = create_sqlite_engine(async_url, echo=cfg.debug)
        else:
            _engine = create_url_engine(async_url, echo=cfg.debug)
    return _engine


_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory  # noqa: PLW0603
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession]:
    factory = _get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
