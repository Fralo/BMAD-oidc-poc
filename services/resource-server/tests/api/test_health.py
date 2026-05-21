"""Tests for GET /health — three readiness probes (DB / Alembic / OIDC discovery).

Story 7.2 reframed the JWKS HTTP probe into a presence check against the
cached `OidcDiscovery` on `app.state` (the lifespan startup hook already
fail-fast'd on any fetch error). The exhaustive JWKS HTTP-shape test
matrix moved into `tests/auth/test_oidc_discovery.py`.

Two test layers remain:
1. Helper-level: `_check_database`, `_check_alembic_at_head`, and
   `_check_oidc_discovery` exercised against mocked dependencies.
2. Orchestration-level: the `/health` endpoint hit via TestClient with
   the three helpers monkey-patched, asserting the 200/503 envelope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from resource_server.api import health as health_module

# ---------------------------------------------------------------------------
# /health orchestration tests
# ---------------------------------------------------------------------------


def _patch_all_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    db: tuple[bool, str] = (True, ""),
    alembic: tuple[bool, str] = (True, ""),
    oidc: tuple[bool, str] = (True, ""),
) -> None:
    monkeypatch.setattr(health_module, "_check_database", AsyncMock(return_value=db))
    monkeypatch.setattr(
        health_module, "_check_alembic_at_head", AsyncMock(return_value=alembic)
    )
    monkeypatch.setattr(
        health_module, "_check_oidc_discovery", MagicMock(return_value=oidc)
    )


async def test_health_returns_200_when_all_probes_ok(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(monkeypatch)

    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_returns_503_envelope_when_db_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(monkeypatch, db=(False, "database unreachable: boom"))

    response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["errorCode"] == "service_unavailable"
    assert body["detail"] == {
        "database": "down",
        "alembic": "ok",
        "oidc_discovery": "ok",
    }


async def test_health_returns_503_when_alembic_not_at_head(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(
        monkeypatch,
        alembic=(False, "alembic not at head: current=None head='0001_init'"),
    )

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["alembic"] == "down"


async def test_health_returns_503_when_oidc_discovery_missing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(
        monkeypatch, oidc=(False, "oidc_discovery not populated on app.state")
    )

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["oidc_discovery"] == "down"


async def test_health_logs_verbose_detail_when_a_probe_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    _patch_all_probes(monkeypatch, db=(False, "database unreachable: boom"))
    with caplog.at_level(logging.WARNING, logger="resource_server.api.health"):
        await client.get("/health")
    assert any("database unreachable: boom" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _check_database helper
# ---------------------------------------------------------------------------


async def test_check_database_returns_ok_when_select_succeeds(engine) -> None:
    ok, detail = await health_module._check_database(engine)
    assert ok is True
    assert detail == ""


async def test_check_database_returns_failure_when_engine_raises() -> None:
    bad_engine = MagicMock()
    bad_engine.connect.side_effect = RuntimeError("boom")
    ok, detail = await health_module._check_database(bad_engine)
    assert ok is False
    assert "database unreachable" in detail
    assert "boom" in detail


# ---------------------------------------------------------------------------
# _check_alembic_at_head helper
# ---------------------------------------------------------------------------


async def test_check_alembic_at_head_passes_when_current_matches_head(
    engine,
) -> None:
    """With current==head, the probe returns success and an empty detail."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS alembic_version "
                "(version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        await conn.execute(text("DELETE FROM alembic_version"))
        await conn.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('0001_init')")
        )

    try:
        fake_script = MagicMock()
        fake_script.get_current_head.return_value = "0001_init"
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                health_module,
                "ScriptDirectory",
                MagicMock(from_config=lambda *_a: fake_script),
            )
            ok, detail = await health_module._check_alembic_at_head(engine)
            assert ok is True, detail
            assert detail == ""
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


async def test_check_alembic_at_head_fails_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a, **_kw):
        raise RuntimeError("alembic blew up")

    monkeypatch.setattr(health_module, "ScriptDirectory", MagicMock(from_config=_boom))
    bad_engine = MagicMock()
    ok, detail = await health_module._check_alembic_at_head(bad_engine)
    assert ok is False
    assert "alembic check failed" in detail
    assert "alembic blew up" in detail


async def test_check_alembic_at_head_fails_when_current_differs_from_head(
    monkeypatch: pytest.MonkeyPatch, engine
) -> None:
    fake_script = MagicMock()
    fake_script.get_current_head.return_value = "0001_init"
    monkeypatch.setattr(
        health_module,
        "ScriptDirectory",
        MagicMock(from_config=lambda *_a: fake_script),
    )
    ok, detail = await health_module._check_alembic_at_head(engine)

    assert ok is False
    assert "alembic not at head" in detail
    assert "current=None" in detail
    assert "head='0001_init'" in detail


# ---------------------------------------------------------------------------
# _check_oidc_discovery helper (Story 7.2: presence check on app.state)
# ---------------------------------------------------------------------------


def test_check_oidc_discovery_returns_ok_when_discovery_present() -> None:
    request = MagicMock()
    request.app.state.oidc_discovery = object()
    ok, detail = health_module._check_oidc_discovery(request)
    assert ok is True
    assert detail == ""


def test_check_oidc_discovery_returns_failure_when_attribute_missing() -> None:
    # Simulate a starlette State that raises on getattr (mirrors the
    # production `_state` dict's __getattr__ behavior for absent keys).
    class _EmptyState:
        oidc_discovery = None

    request = MagicMock()
    request.app.state = _EmptyState()
    ok, detail = health_module._check_oidc_discovery(request)
    assert ok is False
    assert "not populated" in detail
