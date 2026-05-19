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


@pytest.mark.parametrize(
    "method,expected_status",
    # GET hits the stub → 200. HEAD/OPTIONS aren't separately handled at
    # /test/open, so Starlette's router returns 405 for each. The point of
    # the test is that the CSRF middleware DOES NOT short-circuit — proven
    # by reaching the exact downstream status the router would return.
    [("GET", 200), ("HEAD", 405), ("OPTIONS", 405)],
)
async def test_safe_methods_passthrough_without_cookie_or_header(
    client: AsyncClient, method: str, expected_status: int
) -> None:
    response = await client.request(method, "/test/open")
    assert response.status_code == expected_status


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
    # Story 6.4 / A8 amendment: CSP source moved to the SPA SSR edge; the
    # BFF no longer attaches CSP on any response. This regression test stays
    # to lock in that posture — a CSRF 403 from the BFF is JSON and must
    # never carry a Content-Security-Policy header (CSP belongs only on
    # the SPA edge's SSR HTML responses).
    response = await client.post("/test/open", json={"value": "x"})
    assert response.status_code == 403
    assert "content-security-policy" not in response.headers


# -- Hardening regressions (post-review patches) -----------------------------


async def test_post_origin_with_userinfo_rejected(
    client_with_csrf: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # `urlsplit("http://attacker@test")` strips userinfo and returns
    # hostname="test", so a naive tuple comparison would accept it as
    # same-origin. _origin_matches rejects non-canonical Origin headers.
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client_with_csrf.post(
        "/test/open",
        json={"value": "x"},
        headers={"Origin": "http://attacker@test"},
    )
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_origin_mismatch" in r.message for r in caplog.records)


async def test_post_with_malformed_bff_base_url_returns_403(
    client_with_csrf: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Operator misconfig that makes urlsplit raise (IPv6 bracket malformed)
    # must fail-closed via _reject(), not a 500.
    caplog.set_level(logging.ERROR, logger="bff.auth.csrf")
    monkeypatch.setattr(settings, "bff_base_url", "http://[::1")
    response = await client_with_csrf.post("/test/open", json={"value": "x"})
    assert response.status_code == 403
    _assert_reject_envelope(response.json())
    assert any("csrf_misconfig_bff_base_url" in r.message for r in caplog.records)


# -- Path exemption — Story 1.12 ---------------------------------------------


async def test_csrf_exempt_for_test_reset_path(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Story 1.12 carves out `/v1/test/reset` from CSRF enforcement so the
    # bearer-authenticated test-reset endpoint can be reached by the
    # Playwright fixture without minting a CSRF cookie/header pair.
    #
    # In the live test app (built from `bff.main`) the route itself is
    # NOT registered (`settings.enable_test_reset` is False by default),
    # so the request reaches FastAPI's default 404 — what matters here
    # is that the response is NOT a CSRF 403. The exemption WARN log
    # MUST fire to prove the middleware short-circuited.
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post("/v1/test/reset", json={"value": "x"})
    assert response.status_code != 403
    # 404 is the expected fall-through when the route isn't mounted; the
    # important non-regression is that we did NOT 403 the request.
    assert response.status_code == 404
    assert any(
        "csrf_exempt_path" in r.message
        and "path=/v1/test/reset" in r.message
        and "method=POST" in r.message
        for r in caplog.records
    )


async def test_csrf_exempt_for_test_reset_path_with_trailing_slash(
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Patch P2: `/v1/test/reset/` (trailing slash) must ALSO bypass CSRF.
    # FastAPI's `redirect_slashes=True` 307 still flows through the CSRF
    # middleware on the original URL — without the trailing-slash entry
    # in `_CSRF_EXEMPT_PATHS`, this request would 403 BEFORE the
    # slash-redirect could ever fire. Asserts the bypass log line for the
    # exact path the request was made against.
    caplog.set_level(logging.WARNING, logger="bff.auth.csrf")
    response = await client.post("/v1/test/reset/", json={"value": "x"})
    assert response.status_code != 403
    assert any(
        "csrf_exempt_path" in r.message
        and "path=/v1/test/reset/" in r.message
        and "method=POST" in r.message
        for r in caplog.records
    )
