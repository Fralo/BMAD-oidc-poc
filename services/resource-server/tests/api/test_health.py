"""Tests for GET /health — three readiness probes (DB / Alembic / JWKS).

Two test layers:
1. Helper-level: each `_check_*` function is exercised against mocked
   dependencies (DB engine, Alembic config, httpx MockTransport).
2. Orchestration-level: the `/health` endpoint is hit via TestClient with
   the three helpers monkey-patched, asserting the 200/503 envelope
   contract.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from httpx import AsyncClient

from resource_server.api import health as health_module
from resource_server.core.config import AppSettings

# ---------------------------------------------------------------------------
# /health orchestration tests
# ---------------------------------------------------------------------------


def _patch_all_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    db: tuple[bool, str] = (True, ""),
    alembic: tuple[bool, str] = (True, ""),
    jwks: tuple[bool, str] = (True, ""),
) -> None:
    monkeypatch.setattr(health_module, "_check_database", AsyncMock(return_value=db))
    monkeypatch.setattr(
        health_module, "_check_alembic_at_head", AsyncMock(return_value=alembic)
    )
    monkeypatch.setattr(health_module, "_check_jwks", AsyncMock(return_value=jwks))


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
    # Mirrors BFF Story 1.3 Review Findings P4: response detail is
    # sanitized to status labels only ("down"/"ok"); the verbose probe-detail
    # string is logged server-side, not echoed to the unauthenticated caller.
    _patch_all_probes(monkeypatch, db=(False, "database unreachable: boom"))

    response = await client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["errorCode"] == "service_unavailable"
    assert body["detail"] == {
        "database": "down",
        "alembic": "ok",
        "jwks": "ok",
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


async def test_health_returns_503_when_jwks_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_all_probes(monkeypatch, jwks=(False, "jwks returned HTTP 503"))

    response = await client.get("/health")

    assert response.status_code == 503
    assert response.json()["detail"]["jwks"] == "down"


async def test_health_logs_verbose_detail_when_a_probe_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The verbose detail is logged at WARNING level even though the response
    # body only carries sanitized labels — verifies operators still see the
    # real cause server-side. Mirrors BFF P4.
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
        # Mock head to also be '0001_init' so the test is independent of
        # whether real migrations exist in alembic/versions/.
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
        # Engine is session-scoped; a failed assertion above must not leak
        # `alembic_version` into sibling tests.
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
    # `_read_current_revision_sync` returns None (no migration table yet);
    # head is "0001_init" (mocked); current != head ⇒ probe fails.
    ok, detail = await health_module._check_alembic_at_head(engine)

    assert ok is False
    assert "alembic not at head" in detail
    assert "current=None" in detail
    assert "head='0001_init'" in detail


# ---------------------------------------------------------------------------
# _check_jwks helper
# ---------------------------------------------------------------------------


def _settings_with_jwks(jwks_url: str) -> AppSettings:
    cfg = AppSettings()
    cfg.oidc_jwks_url = jwks_url
    return cfg


def _factory_for(transport: httpx.MockTransport):
    def _build(**kw):
        return httpx.AsyncClient(transport=transport, **kw)

    return _build


async def test_check_jwks_returns_failure_when_url_unset() -> None:
    cfg = _settings_with_jwks("")
    ok, detail = await health_module._check_jwks(cfg)
    assert ok is False
    assert detail == "OIDC_JWKS_URL is not configured"


async def test_check_jwks_returns_ok_on_2xx_with_keys_array() -> None:
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ("http://kc/realms/x/protocol/openid-connect/certs")
        return httpx.Response(
            200,
            json={"keys": [{"kty": "RSA", "kid": "abc", "n": "...", "e": "AQAB"}]},
        )

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is True
    assert detail == ""


async def test_check_jwks_returns_ok_on_empty_keys_array() -> None:
    # Empty `keys: []` is liveness-acceptable — a freshly-rotated realm
    # momentarily exposes an empty key set; treating that as a /health
    # failure would create a startup race against Keycloak's cache warm-up.
    # Key-validity is Story 3.2's territory via PyJWKClient.
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": []})

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is True, detail
    assert detail == ""


async def test_check_jwks_rejects_non_json_body() -> None:
    # A 2xx with HTML or empty body must NOT pass the probe — a misconfigured
    # ingress returning a generic 200 OK would otherwise satisfy it without
    # JWKS actually being reachable.
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>generic landing page</html>")

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "non-JSON" in detail


async def test_check_jwks_rejects_json_array_body() -> None:
    # A JSON array is technically valid JSON but is not a JWKS document —
    # must fail the probe.
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "not a JSON object" in detail


async def test_check_jwks_rejects_object_without_keys_field() -> None:
    # A 200 with JSON body that lacks `keys` is NOT a JWKS document.
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unrelated": "payload"})

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "keys" in detail


async def test_check_jwks_rejects_keys_not_a_list() -> None:
    # `keys` present but not a list — defends against pathological upstreams.
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": "not-a-list"})

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "keys" in detail


async def test_check_jwks_returns_failure_on_5xx() -> None:
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is False
    assert "503" in detail


async def test_check_jwks_returns_failure_on_network_error() -> None:
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(_handler)

    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )

    assert ok is False
    assert "jwks unreachable" in detail
    assert "connection refused" in detail


async def test_check_jwks_returns_failure_on_timeout() -> None:
    cfg = _settings_with_jwks("http://kc/realms/x/protocol/openid-connect/certs")

    def _handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    transport = httpx.MockTransport(_handler)
    ok, detail = await health_module._check_jwks(
        cfg, client_factory=_factory_for(transport)
    )
    assert ok is False
    assert "jwks unreachable" in detail
