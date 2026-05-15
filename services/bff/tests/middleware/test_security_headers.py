"""SecurityHeadersMiddleware route-level tests (Story 1.6, AC11 scenarios 24-30).

Byte-for-byte assertion on the CSP header value catches whitespace / quoting
drift; path-prefix tests cover the JSON-API exclusion list.
"""

import pytest
from httpx import AsyncClient

_EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)

_HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9"


# -- CSP attached on SPA-serving routes (scenarios 24, 28, 30) ----------------


async def test_csp_attached_on_catch_all_with_html_accept(
    client: AsyncClient,
) -> None:
    # Scenario 24 + 28 — unknown path falls through to the default 404, but
    # the path is NOT in the API exclusion list (/auth/, /api/, /v1/, /health),
    # so the middleware attaches CSP because Accept includes text/html.
    response = await client.get("/some-unknown-path", headers={"Accept": "text/html"})
    assert response.status_code == 404
    assert "content-security-policy" in response.headers
    assert response.headers["content-security-policy"] == _EXPECTED_CSP


async def test_csp_header_value_byte_for_byte(client: AsyncClient) -> None:
    # Scenario 30 — explicit byte-for-byte equality on an HTML response.
    response = await client.get("/", headers={"Accept": _HTML_ACCEPT})
    assert response.headers.get("content-security-policy") == _EXPECTED_CSP


# -- CSP NOT attached on JSON API surfaces (scenarios 25, 26, 27, 29) --------


async def test_csp_not_attached_on_api_me_401(client: AsyncClient) -> None:
    # Scenario 25 — `/api/me` returns 401 session_expired without a cookie.
    # Path prefix `/api/` excludes it from CSP attach.
    response = await client.get("/api/me")
    assert response.status_code == 401
    assert "content-security-policy" not in response.headers


async def test_csp_not_attached_on_health(client: AsyncClient) -> None:
    # Scenario 26 — `/health` may hit OIDC discovery and return 503 in test;
    # CSP exclusion is path-driven, status-independent.
    response = await client.get("/health")
    assert "content-security-policy" not in response.headers


async def test_csp_not_attached_on_health_with_html_accept(
    client: AsyncClient,
) -> None:
    # Belt-and-braces: even if a curious caller probes `/health` with
    # Accept: text/html, the bare-leaf path exclusion (not a prefix) still
    # suppresses CSP.
    response = await client.get("/health", headers={"Accept": _HTML_ACCEPT})
    assert "content-security-policy" not in response.headers


async def test_csp_not_attached_on_v1_unknown_path(client: AsyncClient) -> None:
    # Scenario 27 — `/v1/*` JSON API namespace excluded regardless of status.
    response = await client.get("/v1/nope")
    assert response.status_code == 404
    assert "content-security-policy" not in response.headers


async def test_csp_not_attached_on_json_accept(client: AsyncClient) -> None:
    # Scenario 29 — same unknown path as #24, but Accept: application/json
    # disables the HTML content-negotiation guard. No CSP.
    response = await client.get("/random", headers={"Accept": "application/json"})
    assert "content-security-policy" not in response.headers


async def test_csp_not_attached_on_auth_login_redirect(
    client_no_redirects: AsyncClient,
) -> None:
    # Belt-and-braces: `/auth/login` is a GET that 302s. Even if a future
    # browser sent Accept: text/html on it, the path-prefix exclusion `/auth/`
    # keeps CSP off the redirect response.
    response = await client_no_redirects.get(
        "/auth/login", headers={"Accept": _HTML_ACCEPT}
    )
    assert "content-security-policy" not in response.headers


@pytest.mark.parametrize("bare_path", ["/auth", "/api", "/v1"])
async def test_csp_not_attached_on_bare_api_namespace_roots(
    client: AsyncClient, bare_path: str
) -> None:
    # Post-review patch — bare namespace roots without trailing slash slipped
    # through the prefix check and would have received CSP on the 404 JSON
    # response. Now they are exact-matched against _API_PATHS_EXACT.
    response = await client.get(bare_path, headers={"Accept": _HTML_ACCEPT})
    assert "content-security-policy" not in response.headers
