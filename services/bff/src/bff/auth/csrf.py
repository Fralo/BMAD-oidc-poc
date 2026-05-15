"""Double-submit CSRF middleware per architecture A5.

Exempts safe methods (GET/HEAD/OPTIONS); enforces `X-CSRF-Token` ==
`bff_csrf` cookie AND a same-origin `Origin` (with `Referer` fallback) on
every state-changing request. Rejections short-circuit with the documented
403 `csrf_invalid` envelope (architecture C5).

The middleware is read-only with respect to cookies — the `bff_csrf` cookie
is minted at `/auth/callback` time (Story 1.5) and cleared at
`/auth/logout` (Story 1.7). This module never mints or rotates it.
"""

import hmac
import logging
from typing import Final
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from bff.core.config import settings
from bff.core.errors import ErrorCode

logger = logging.getLogger(__name__)

_SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS"})
_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}


class CsrfMiddleware(BaseHTTPMiddleware):
    """Enforces double-submit cookie + custom header + Origin/Referer check."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method.upper() in _SAFE_METHODS:
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

        expected = self._parse_origin(settings.bff_base_url)
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
            content={
                "errorCode": ErrorCode.CSRF_INVALID.code,
                "message": ErrorCode.CSRF_INVALID.message,
                "detail": None,
            },
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

    @classmethod
    def _origin_matches(
        cls, observed: str, expected: tuple[str, str, int | None]
    ) -> bool:
        try:
            return cls._parse_origin(observed) == expected
        except ValueError:
            return False
