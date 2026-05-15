"""CsrfMiddleware route-level tests (Story 1.6, AC11 scenarios 1-23, 31).

The tests target the `POST /test/open` stub welded to the live app by
`tests/conftest.py`. The CSRF middleware runs in front of every router
include, so any state-changing request flowing through the bare `client`
fixture (no cookies, no header) MUST hit the 403 short-circuit — which is
exactly the demonstration in scenario 22.
"""

import logging

import pytest
from httpx import AsyncClient

from bff.core.config import settings
from bff.core.errors import ErrorCode

_CSRF_VALUE = "test-csrf-secret-43chars-xxxxxxxxxxxxxxxxxxx"
_REJECT_BODY = {
    "errorCode": ErrorCode.CSRF_INVALID.code,
    "message": ErrorCode.CSRF_INVALID.message,
    "detail": None,
}


def _assert_reject_envelope(response_body: dict) -> None:
    assert response_body == _REJECT_BODY


# -- Safe methods (scenarios 1-3) ---------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
async def test_safe_methods_passthrough_without_cookie_or_header(
    client: AsyncClient, method: str
) -> None:
    response = await client.request(method, "/test/open")
    # GET → 200 stub payload; HEAD → 200 (FastAPI auto-handles); OPTIONS → 405
    # from Starlette's default method-not-allowed (no OPTIONS handler defined).
    # Middleware MUST NOT short-circuit any of these regardless of status.
    assert response.status_code in {200, 405}
    assert (
        response.headers.get("content-type", "").startswith(
            ("application/json", "text/plain")
        )
        or response.status_code == 200
    )


# -- Happy path state-changing (scenarios 4-7) -------------------------------


async def test_post_happy_path(client_with_csrf: AsyncClient) -> None:
    response = await client_with_csrf.post("/test/open", json={"value": "hello"})
    assert response.status_code == 201
    assert response.json() == {"value": "hello"}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
async def test_other_state_changing_methods_pass_middleware(
    client_with_csrf: AsyncClient, method: str
) -> None:
    # No PUT/PATCH/DELETE route exists at /test/open → router returns 405. The
    # middleware's job is to NOT short-circuit; the 405 is downstream proof
    # call_next was invoked.
    response = await client_with_csrf.request(method, "/test/open")
    assert response.status_code == 405


# -- Header missing / empty (scenarios 8, 9) ---------------------------------


async def test_post_missing_header_returns_403(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_header_missing" in r.message for r in caplog.records)


async def test_post_empty_header_returns_403(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={"X-CSRF-Token": ""},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_header_missing" in r.message for r in caplog.records)


# -- Cookie missing / empty / mismatch (scenarios 10, 11, 12) ----------------


async def test_post_missing_cookie_returns_403(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        headers={"X-CSRF-Token": _CSRF_VALUE, "Origin": "http://test"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_token_mismatch" in r.message for r in caplog.records)


async def test_post_empty_cookie_returns_403(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: ""},
        headers={"X-CSRF-Token": _CSRF_VALUE, "Origin": "http://test"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_token_mismatch" in r.message for r in caplog.records)


async def test_post_header_cookie_mismatch_returns_403(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: "abc"},
        headers={"X-CSRF-Token": "xyz", "Origin": "http://test"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_token_mismatch" in r.message for r in caplog.records)


async def test_post_length_mismatch_returns_403(
    client: AsyncClient,
) -> None:
    # Scenario 21 — header and cookie differ in length. compare_digest's
    # length-leak is by design here (the secret is fixed-length by spec).
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: "abc"},
        headers={"X-CSRF-Token": "abcd", "Origin": "http://test"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())


# -- Origin / Referer (scenarios 13-20) --------------------------------------


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",  # scenario 13: cross-host
        "http://test:9999",  # scenario 14: cross-port
        "https://test",  # scenario 15: scheme mismatch
    ],
)
async def test_post_cross_origin_returns_403(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    origin: str,
) -> None:
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={"X-CSRF-Token": _CSRF_VALUE, "Origin": origin},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_origin_mismatch" in r.message for r in caplog.records)


async def test_post_origin_absent_referer_same_origin_passes(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Scenario 16 — Origin absent, Referer present and same-origin. httpx's
    # AsyncClient adds Origin only on POST when explicitly set; passing
    # headers without Origin keeps it absent.
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    response = await client.post(
        "/test/open",
        json={"value": "ok"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={
            "X-CSRF-Token": _CSRF_VALUE,
            "Referer": "http://test/some/page?q=1",
        },
    )
    assert response.status_code == 201
    assert response.json() == {"value": "ok"}


async def test_post_origin_absent_referer_cross_origin_returns_403(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={
            "X-CSRF-Token": _CSRF_VALUE,
            "Referer": "https://evil.example/x",
        },
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_origin_mismatch" in r.message for r in caplog.records)


async def test_post_origin_and_referer_absent_returns_403(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={"X-CSRF-Token": _CSRF_VALUE},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_origin_mismatch" in r.message for r in caplog.records)


async def test_post_origin_null_no_referer_returns_403(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Scenario 19 — sandboxed iframe / data: URL. `Origin: null` is the RFC
    # 6454 sentinel value; must be treated as not-same-origin.
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post(
        "/test/open",
        json={"value": "x"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={"X-CSRF-Token": _CSRF_VALUE, "Origin": "null"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_origin_mismatch" in r.message for r in caplog.records)


async def test_post_origin_null_referer_same_origin_passes(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Scenario 20 — Origin: null but Referer is same-origin → fallback to
    # Referer succeeds.
    monkeypatch.setattr(settings, "bff_base_url", "http://test")
    response = await client.post(
        "/test/open",
        json={"value": "ok"},
        cookies={settings.bff_csrf_cookie_name: _CSRF_VALUE},
        headers={
            "X-CSRF-Token": _CSRF_VALUE,
            "Origin": "null",
            "Referer": "http://test/x",
        },
    )
    assert response.status_code == 201
    assert response.json() == {"value": "ok"}


# -- Wiring proofs (scenarios 22, 23) ----------------------------------------


async def test_existing_post_open_requires_csrf_via_bare_client(
    client: AsyncClient,
) -> None:
    # Scenario 22 — the bare `client` fixture has no CSRF setup. With the
    # middleware wired into main.py, POST /test/open MUST now 403. Proves the
    # middleware is active in the live app stack.
    response = await client.post("/test/open", json={"value": "x"})
    assert response.status_code == 403
    _assert_reject_envelope(response.json())


async def test_client_with_csrf_fixture_round_trips(
    client_with_csrf: AsyncClient,
) -> None:
    # Scenario 23 — inverse of #22. The fixture pre-seeds cookie + header +
    # Origin; POST /test/open returns the stub payload.
    response = await client_with_csrf.post("/test/open", json={"value": "ok"})
    assert response.status_code == 201
    assert response.json() == {"value": "ok"}


# -- Middleware-ordering proof (scenario 31) ---------------------------------


async def test_csrf_reject_carries_no_csp_header(client: AsyncClient) -> None:
    # SecurityHeadersMiddleware is INNER to CsrfMiddleware in the LIFO onion.
    # A CSRF short-circuit therefore bypasses the CSP attach step — the 403
    # is JSON and must not carry a Content-Security-Policy header.
    response = await client.post("/test/open", json={"value": "x"})
    assert response.status_code == 403
    assert "content-security-policy" not in response.headers
