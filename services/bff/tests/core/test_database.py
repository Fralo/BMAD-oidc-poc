import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import StaticPool

from bff.core import database
from bff.core.config import AppSettings


async def test_get_engine_without_settings_builds_default_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_session_factory", None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DEBUG", "false")

    try:
        engine = database.get_engine()

        assert "aiosqlite" in str(engine.url)
        assert isinstance(engine.pool, StaticPool)
    finally:
        await database.dispose_engine()


async def test_get_session_yields_async_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_session_factory", None)
    try:
        database.get_engine()

        generator = database.get_session()
        session = await generator.__anext__()

        assert isinstance(session, AsyncSession)

        with pytest.raises(StopAsyncIteration):
            await generator.__anext__()
    finally:
        await database.dispose_engine()


async def test_dispose_engine_resets_global_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_session_factory", None)
    database.get_engine()

    await database.dispose_engine()

    assert database._engine is None
    assert database._session_factory is None


async def test_invalid_database_url_raises_at_engine_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await database.dispose_engine()
    monkeypatch.setattr(database, "_engine", None)
    monkeypatch.setattr(database, "_session_factory", None)
    invalid_settings = AppSettings(
        bff_client_secret="test-secret", database_url="not-a-valid-url://"
    )
    monkeypatch.setattr(database, "_default_settings", invalid_settings)
    with pytest.raises(ValueError, match="Invalid DATABASE_URL"):
        database.get_engine()
