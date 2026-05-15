"""Tests for GET /health — three readiness probes (DB / Alembic / OIDC discovery).

Two test layers:
1. Helper-level: each `_check_*` function is exercised against mocked
   dependencies (DB engine, Alembic config, httpx MockTransport).
2. Orchestration-level: the `/health` endpoint is hit via TestClient with the
   three helpers monkey-patched, asserting the 200/503 envelope contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient

from bff.api import health as health_module
from bff.core.config import AppSettings

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
        health_module, "_check_oidc_discovery", AsyncMock(return_value=oidc)
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
    # Story 1.3 Review Findings P4: response detail is sanitized to status
    # labels only ("down"/"ok"); the verbose probe-detail string is logged
    # server-side, not echoed to the unauthenticated caller.
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


async def test_health_returns_503_when_oidc_discovery_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(monkeypatch, oidc=(False, "oidc discovery returned HTTP 503"))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["oidc_discovery"] == "down"


async def test_health_logs_verbose_detail_when_a_probe_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The verbose detail is logged at WARNING level even though the response
    # body only carries sanitized labels — verifies operators still see the
    # real cause server-side.
    import logging

    _patch_all_probes(monkeypatch, db=(False, "database unreachable: boom"))
    with caplog.at_level(logging.WARNING, logger="bff.api.health"):
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


async def test_check_alembic_at_head_passes_with_no_migrations(engine) -> None:
    """With zero migrations defined, head=None and current=None ⇒ at head."""
    ok, detail = await health_module._check_alembic_at_head(engine)
    assert ok is True, detail
    assert detail == ""


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
    # `_read_current_revision_sync` returns None (no migration table yet);
    # head is "0001_init" (mocked); current != head ⇒ probe fails.
    ok, detail = await health_module._check_alembic_at_head(engine)

    assert ok is False
    assert "alembic not at head" in detail
    assert "current=None" in detail
    assert "head='0001_init'" in detail


# ---------------------------------------------------------------------------
# _check_oidc_discovery helper
# ---------------------------------------------------------------------------


def _settings_with_issuer(issuer: str) -> AppSettings:
    cfg = AppSettings()
    cfg.oidc_issuer_url = issuer
    return cfg


def _factory_for(transport: httpx.MockTransport):
    def _build(**kw):
        return httpx.AsyncClient(transport=transport, **kw)

    return _build


async def test_check_oidc_discovery_returns_failure_when_issuer_unset() -> None:
    cfg = _settings_with_issuer("")
    ok, detail = await health_module._check_oidc_discovery(cfg)
    assert ok is False
    assert detail == "OIDC_ISSUER_URL is not configured"


async def test_check_oidc_discovery_returns_ok_on_2xx_response() -> None:
    cfg = _settings_with_issuer("http://kc/realms/x")

    def _handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "http://kc/realms/x/.well-known/openid-configuration"
        )
        return httpx.Response(200, json={"issuer": "http://kc/realms/x"})

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is True
    assert detail == ""


async def test_check_oidc_discovery_rejects_non_json_body() -> None:
    # Story 1.3 Review Findings P5: a 2xx with HTML or empty body must NOT
    # pass the probe — a misconfigured ingress returning a generic 200 OK
    # would otherwise satisfy it without OIDC actually being reachable.
    cfg = _settings_with_issuer("http://kc/realms/x")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>generic landing page</html>")

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "non-JSON" in detail


async def test_check_oidc_discovery_rejects_issuer_mismatch() -> None:
    cfg = _settings_with_issuer("http://kc/realms/x")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"issuer": "http://kc/realms/different"})

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "issuer mismatch" in detail


async def test_check_oidc_discovery_returns_failure_on_5xx() -> None:
    cfg = _settings_with_issuer("http://kc/realms/x")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is False
    assert "503" in detail


async def test_check_oidc_discovery_returns_failure_on_network_error() -> None:
    cfg = _settings_with_issuer("http://kc/realms/x")

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is False
    assert "oidc discovery unreachable" in detail
    assert "connection refused" in detail


async def test_check_oidc_discovery_strips_trailing_slash_on_issuer() -> None:
    cfg = _settings_with_issuer("http://kc/realms/x/")
    seen_urls: list[str] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        # After P5 the probe also validates that the body declares the
        # canonical issuer (trailing slash stripped) — return a matching
        # JSON document.
        return httpx.Response(200, json={"issuer": "http://kc/realms/x"})

    transport = httpx.MockTransport(_handler)

    ok, _ = await health_module._check_oidc_discovery(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is True
    assert seen_urls == ["http://kc/realms/x/.well-known/openid-configuration"]
