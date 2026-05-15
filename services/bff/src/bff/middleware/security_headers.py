"""SPA Content-Security-Policy response-header middleware per architecture A8.

Attaches the documented CSP header to SPA-serving (HTML) responses; leaves
JSON API surfaces (`/auth/*`, `/api/*`, `/v1/*`, `/health`) untouched.

The CSP value is the exact string mandated by architecture A8 — any drift
(extra whitespace, missing directive) is caught by the byte-for-byte
assertion in tests/middleware/test_security_headers.py.
"""

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_CSP_VALUE: Final[str] = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)

_API_PATH_PREFIXES: Final[tuple[str, ...]] = ("/auth/", "/api/", "/v1/")
# Bare JSON-API namespace roots (no trailing slash). Without these, a request
# to `/auth` with `Accept: text/html` slips past the prefix check above (which
# only matches `/auth/`) and would receive CSP on a 404 JSON response.
_API_PATHS_EXACT: Final[frozenset[str]] = frozenset({"/health", "/auth", "/api", "/v1"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Pure additive: attaches CSP on HTML responses to SPA-serving routes."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if self._is_html_request(request) and not self._is_api_path(request.url.path):
            response.headers["Content-Security-Policy"] = _CSP_VALUE
        return response

    @staticmethod
    def _is_html_request(request: Request) -> bool:
        accept = request.headers.get("accept") or ""
        return "text/html" in accept

    @staticmethod
    def _is_api_path(path: str) -> bool:
        if path in _API_PATHS_EXACT:
            return True
        return any(path.startswith(prefix) for prefix in _API_PATH_PREFIXES)
