"""Double-submit CSRF middleware per architecture A5.

Exempts safe methods (GET/HEAD/OPTIONS); enforces `X-CSRF-Token` ==
`bff_csrf` cookie AND a same-origin `Origin` (with `Referer` fallback) on
every state-changing request. Rejections short-circuit with the documented
403 `csrf_invalid` envelope (architecture C5).

The middleware is read-only with respect to cookies — the `bff_csrf` cookie
is minted at `/auth/callback` time (Story 1.5) and cleared at
`/auth/logout` (Story 1.7). This module never mints or rotates it.

`POST /v1/test/reset` is exempt from CSRF enforcement (Story 1.12); it
authenticates via a shared bearer token (`Authorization: Bearer ...`)
instead. The exemption is hard-coded as a single path in
`_CSRF_EXEMPT_PATHS` so a misconfiguration cannot broaden it.
"""

import hmac
import logging
from typing import Final
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from bff.core.config import settings
from bff.core.errors import ErrorCode, build_error_body

logger = logging.getLogger(__name__)

_SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS"})
_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}

# Paths exempted from CSRF enforcement (Story 1.12). Currently only the
# test-reset endpoint, which authenticates via a shared bearer token and
# is itself gated behind `ENABLE_TEST_RESET=true`. The route is only
# mounted when that gate is on; the exemption here is unconditional on
# the gate so a malicious POST under gate-off still bypasses CSRF — but
# it then hits FastAPI's default 404 (no handler is registered), which
# is acceptable because there's no state-change downstream. Hard-coded
# strings (not a prefix, not a config var) so an operator can't broaden
# the exemption via env. Both the canonical path and its trailing-slash
# variant are listed because FastAPI's `redirect_slashes=True` 307 still
# flows through this middleware on the original request URL — a POST to
# `/v1/test/reset/` without the explicit entry would 403 here BEFORE
# the slash-redirect ever fires.
_CSRF_EXEMPT_PATHS: Final[frozenset[str]] = frozenset(
    {"/v1/test/reset", "/v1/test/reset/"}
)


class CsrfMiddleware(BaseHTTPMiddleware):
    """Enforces double-submit cookie + custom header + Origin/Referer check."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method.upper() in _SAFE_METHODS:
            return await call_next(request)

        if request.url.path in _CSRF_EXEMPT_PATHS:
            # Story 1.12: bearer-authenticated test-reset endpoint. Log
            # the exemption at WARN so an operator auditing logs can see
            # which paths bypassed the middleware.
            logger.warning(
                "csrf_exempt_path path=%s method=%s",
                request.url.path,
                request.method,
            )
            return await call_next(request)

        cookie_value = request.cookies.get(settings.bff_csrf_cookie_name) or ""
        # Lowercase header key is the documented Starlette idiom; the mapping is
        # case-insensitive but consistent lowercase reads match the project
        # convention used in api/me.py and api/auth.py.
        header_value = request.headers.get("x-csrf-token") or ""

        if not header_value:
            logger.warning(
                "csrf_header_missing path=%s method=%s",
                request.url.path,
                request.method,
            )
            return self._reject()

        # compare_digest needs bytes-of-equal-length for constant-time behavior.
        # The CSRF secret is a fixed-length token_urlsafe(32) output (Story
        # 1.5), so a length mismatch is a planted-attacker signal — leaking
        # one bit of length is acceptable here.
        if not cookie_value or not hmac.compare_digest(
            header_value.encode("utf-8"), cookie_value.encode("utf-8")
        ):
            logger.warning(
                "csrf_token_mismatch path=%s method=%s",
                request.url.path,
                request.method,
            )
            return self._reject()

        try:
            expected = self._parse_origin(settings.bff_base_url)
        except ValueError, TypeError:
            # bff_base_url is operator-controlled; misconfiguration must
            # fail-closed with the documented 403 rather than a 500.
            logger.error(
                "csrf_misconfig_bff_base_url path=%s method=%s",
                request.url.path,
                request.method,
            )
            return self._reject()
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")

        if origin and origin != "null":
            observed_match = self._origin_matches(origin, expected)
        elif referer:
            observed_match = self._origin_matches(referer, expected)
        else:
            observed_match = False

        if not observed_match:
            referer_host = "(none)"
            if referer:
                try:
                    referer_host = urlsplit(referer).hostname or "(unparseable)"
                except ValueError:
                    referer_host = "(unparseable)"
            logger.warning(
                "csrf_origin_mismatch path=%s origin=%s referer_host=%s",
                request.url.path,
                origin or "(none)",
                referer_host,
            )
            return self._reject()

        return await call_next(request)

    @staticmethod
    def _reject() -> JSONResponse:
        return JSONResponse(
            status_code=ErrorCode.CSRF_INVALID.http_status,
            content=build_error_body(
                ErrorCode.CSRF_INVALID.code,
                ErrorCode.CSRF_INVALID.message,
            ),
        )

    @staticmethod
    def _parse_origin(url: str) -> tuple[str, str, int | None]:
        parts = urlsplit(url)
        scheme = parts.scheme
        hostname = parts.hostname or ""
        port = parts.port
        if port is None:
            port = _DEFAULT_PORTS.get(scheme)
        return (scheme, hostname, port)

    @staticmethod
    def _origin_matches(observed: str, expected: tuple[str, str, int | None]) -> bool:
        try:
            parts = urlsplit(observed)
            # `urlsplit("http://attacker@host")` silently strips the userinfo
            # and yields hostname="host" — without this guard the (scheme,
            # host, port) tuple would compare equal to a legitimate
            # same-origin expected value. Path/query/fragment are not
            # security-relevant here because the tuple comparison already
            # ignores them (Referer headers legitimately carry a path).
            if parts.username or parts.password:
                return False
            return CsrfMiddleware._parse_origin(observed) == expected
        except ValueError:
            return False
