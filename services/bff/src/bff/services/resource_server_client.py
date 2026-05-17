"""BFF → Resource Server HTTP client (Story 3.5).

Wraps a plain ``httpx.AsyncClient`` with:

* The architectural BFF→RS timeout budget per AR19 / architecture §C6 — 5s
  connect, 10s read; zero retries on 5xx.
* The architectural marquee 401-refresh-replay cycle (NFR3 / architecture §A6)
  — when the RS returns 401 on a request carrying a possibly-expired
  ``access_token``, the client exchanges the session's ``refresh_token`` at
  Keycloak's ``/token`` endpoint and replays the RS call exactly once with the
  fresh access_token. Single cycle only — no further retries regardless of
  the retry's outcome.
* The FR-ERROR-01 / J6 honest-failure surface — any ``httpx`` transport
  failure or RS 5xx response is normalized to ``RsUnavailable`` so the proxy
  router can emit the project-standard ``503 resource_server_unavailable``
  envelope without fabricating a result.
* NFR6 identity propagation — ``sub`` is NEVER added to the request body,
  path, or query string; the RS reads it from the JWT only (architecture
  line 1141).

Public API:
    * ``ResourceServerClient`` — the client class.
    * ``resource_server_client`` — a module-level singleton built from the
      global ``settings`` instance (mirrors ``api/me.py``'s
      ``_session_service = SessionService()`` pattern but exposed publicly
      since the proxy router needs to import a pre-built instance).
    * ``RsUnavailable`` — raised on transport failure or RS 5xx; carries a
      ``cause`` classifier (used for WARN logging) and the originating
      ``http_status`` when known.
    * ``RsSessionTerminated`` — raised when the refresh-and-replay cycle
      cannot recover (refresh failed → ``clear_cookies=True``; refresh
      succeeded but retry still 401 → ``clear_cookies=False``).

Compute-estimate (Epic 4 Story 4.2) will land as a third public method on
this class. Story 3.5 explicitly does NOT pre-stage that method.

References
----------
- epics.md §Story 3.5 lines 1326-1373
- architecture.md §A6 line 352 (token refresh strategy)
- architecture.md §C6 line 413 (BFF→RS timeouts)
- architecture.md §NFR3 line 38 (transparent token refresh)
- architecture.md §NFR6 line 1141 (identity propagation)
- PRD §FR-ERROR-01 (honest J6 failure)
- services/bff/src/bff/auth/keycloak_cookie_session.py:34 (the httpx
  Timeout idiom mirrored here)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from bff.core.config import AppSettings, settings
from bff.models.entities.session import Session
from bff.services.session_service import SessionService

logger = logging.getLogger(__name__)

# AR19 / architecture §C6 — 5s connect, 10s read; zero retries on 5xx.
# Mirrored on the Keycloak `/token` refresh call (same upstream budget per
# architecture §C6's BFF→Keycloak row).
_RS_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
_READING_SPEED_PATH = "/v1/reading-speed"
_TOKEN_PATH_SUFFIX = "/protocol/openid-connect/token"


class RsUnavailable(Exception):  # noqa: N818 -- domain classifier; not a stack-trace error
    """Raised when the RS is unreachable or returns 5xx.

    The proxy router catches this and emits the project-standard ``503
    resource_server_unavailable`` envelope per FR-ERROR-01 / AR17.

    Attributes
    ----------
    cause:
        Short classifier for WARN logging (``"connect_error"``,
        ``"connect_timeout"``, ``"read_timeout"``, ``"write_timeout"``,
        ``"pool_timeout"``, ``"network_error"``, ``"rs_5xx_response"``,
        ``"unknown_transport"``). Never contains token material.
    http_status:
        The RS's response status code when the failure was a 5xx
        response; ``None`` for transport-level failures.
    """

    def __init__(self, cause: str, http_status: int | None = None) -> None:
        self.cause = cause
        self.http_status = http_status
        super().__init__(cause)


class RsSessionTerminated(Exception):  # noqa: N818 -- control-flow signal, not an Error
    """Raised when the refresh-and-replay cycle cannot recover.

    Attributes
    ----------
    clear_cookies:
        ``True`` when the refresh itself failed (Keycloak rejected the
        refresh_token, network error, malformed response). The proxy
        router emits a 401 with both the session cookie and the
        ``csrf_token`` cookie cleared (Max-Age=0).
        ``False`` when refresh succeeded but the retry still returned 401
        (unusual: indicates scope/audience drift). The proxy emits a 401
        WITHOUT clearing cookies — the SPA's /login redirect produces a
        fresh login that will overwrite the session on success.
    """

    def __init__(self, *, clear_cookies: bool) -> None:
        self.clear_cookies = clear_cookies
        super().__init__("session_terminated")


class _RefreshFailed(Exception):  # noqa: N818 -- internal classifier
    """Internal classifier for Keycloak `/token` refresh-grant failures."""

    def __init__(self, cause: str) -> None:
        self.cause = cause
        super().__init__(cause)


def _classify_transport_error(exc: httpx.HTTPError) -> str:
    """Map an httpx exception to the WARN-log classifier string."""
    if isinstance(exc, httpx.ConnectTimeout):
        return "connect_timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.ReadTimeout):
        return "read_timeout"
    if isinstance(exc, httpx.WriteTimeout):
        return "write_timeout"
    if isinstance(exc, httpx.PoolTimeout):
        return "pool_timeout"
    if isinstance(exc, httpx.NetworkError):
        return "network_error"
    return "unknown_transport"


class ResourceServerClient:
    """HTTP client for the BFF→RS link with refresh-and-replay."""

    def __init__(
        self,
        settings_obj: AppSettings,
        session_service: SessionService | None = None,
    ) -> None:
        self._settings = settings_obj
        self._session_service = session_service or SessionService()

    async def get_reading_speed(
        self, db: AsyncSession, session_row: Session
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``GET /v1/reading-speed`` with refresh-and-replay.

        Returns ``(http_status, parsed_json_body_or_None)``. Raises
        :class:`RsUnavailable` on transport failure or RS 5xx;
        :class:`RsSessionTerminated` when the refresh cycle cannot
        recover.
        """
        return await self._call_with_refresh(db, session_row, method="GET", body=None)

    async def put_reading_speed(
        self, db: AsyncSession, session_row: Session, payload: dict[str, Any]
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``PUT /v1/reading-speed`` with the JSON ``payload``.

        Same return / raise contract as :meth:`get_reading_speed`. The
        ``payload`` is forwarded verbatim — NO ``sub`` injection per
        NFR6.
        """
        return await self._call_with_refresh(
            db, session_row, method="PUT", body=payload
        )

    async def _call_with_refresh(
        self,
        db: AsyncSession,
        session_row: Session,
        *,
        method: str,
        body: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None]:
        # First attempt with the current access_token.
        status, parsed = await self._do_rs_call(method, session_row.access_token, body)
        if status != 401:
            return status, parsed

        # RS-401 → attempt refresh-and-replay (single cycle per AR19 / A6).
        try:
            new_tokens = await self._refresh_access_token(session_row)
        except _RefreshFailed as exc:
            # Refresh itself failed — clear session row + emit cookie-clearing 401.
            logger.warning(
                "refresh_failed cause=%s sub=%s session=%s...",
                exc.cause,
                session_row.sub,
                session_row.id[:8],
            )
            await self._session_service.delete_session(db, session_id=session_row.id)
            raise RsSessionTerminated(clear_cookies=True) from exc

        # Persist the rotated tokens BEFORE the retry so a crash mid-retry
        # leaves the session in a forward-only state (next request will use
        # the fresh access_token).
        await self._persist_refreshed_tokens(db, session_row, new_tokens)

        retry_status, retry_parsed = await self._do_rs_call(
            method, new_tokens["access_token"], body
        )
        if retry_status == 401:
            # Retry still 401 — refresh worked but RS still rejected.
            # AC4 case 5: leave session in place; emit 401 without
            # clearing cookies. The SPA's /login redirect produces a new
            # login that overwrites the session on success.
            logger.warning(
                "rs_401_after_refresh sub=%s session=%s...",
                session_row.sub,
                session_row.id[:8],
            )
            raise RsSessionTerminated(clear_cookies=False)
        return retry_status, retry_parsed

    async def _do_rs_call(
        self,
        method: str,
        access_token: str,
        body: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue a single RS HTTP call. Normalize failures to RsUnavailable."""
        url = self._settings.rs_base_url.rstrip("/") + _READING_SPEED_PATH
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=_RS_TIMEOUT) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=body)
                else:  # pragma: no cover -- only GET/PUT shapes are wired
                    msg = f"unsupported method: {method}"
                    raise ValueError(msg)
        except httpx.HTTPError as exc:
            cause = _classify_transport_error(exc)
            logger.warning(
                "resource_server_unavailable cause=%s http_status=None",
                cause,
            )
            raise RsUnavailable(cause) from exc

        if response.status_code >= 500:
            logger.warning(
                "resource_server_unavailable cause=rs_5xx_response http_status=%s",
                response.status_code,
            )
            raise RsUnavailable("rs_5xx_response", http_status=response.status_code)

        # Parse body lazily; some statuses (rare here, but defensive)
        # may return an empty body.
        if not response.content:
            return response.status_code, None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict) and parsed is not None:
            # The RS contract emits dicts; a list or scalar would be a
            # contract regression. Surface it as a parse failure (None body
            # forwarded with the original status) rather than crash the
            # proxy router.
            parsed = None
        return response.status_code, parsed

    async def _refresh_access_token(self, session_row: Session) -> dict[str, Any]:
        """Exchange refresh_token for a new access_token at Keycloak.

        Mirrors the BFF's existing ``keycloak_cookie_session.exchange_code``
        timeout idiom (Story 1.5). Uses a plain httpx POST with form-encoded
        body — Keycloak's confidential-client refresh grant accepts
        ``client_id`` and ``client_secret`` as form fields.

        Raises ``_RefreshFailed`` on any failure mode. The caller surfaces
        this as ``RsSessionTerminated(clear_cookies=True)``.
        """
        token_url = self._settings.oidc_issuer_url.rstrip("/") + _TOKEN_PATH_SUFFIX
        try:
            async with httpx.AsyncClient(timeout=_RS_TIMEOUT) as client:
                response = await client.post(
                    token_url,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": session_row.refresh_token,
                        "client_id": self._settings.oidc_client_id,
                        "client_secret": self._settings.bff_client_secret,
                    },
                )
        except httpx.HTTPError as exc:
            msg = f"transport_error:{type(exc).__name__}"
            raise _RefreshFailed(msg) from exc

        if 400 <= response.status_code < 500:
            msg = f"keycloak_4xx:{response.status_code}"
            raise _RefreshFailed(msg)
        if response.status_code >= 500:
            msg = f"keycloak_5xx:{response.status_code}"
            raise _RefreshFailed(msg)
        try:
            payload = response.json()
        except ValueError as exc:
            raise _RefreshFailed("malformed_response") from exc
        if not isinstance(payload, dict):
            raise _RefreshFailed("malformed_response")
        if "access_token" not in payload or "refresh_token" not in payload:
            raise _RefreshFailed("malformed_response")
        return payload

    async def _persist_refreshed_tokens(
        self,
        db: AsyncSession,
        session_row: Session,
        tokens: dict[str, Any],
    ) -> None:
        """Update the sessions row with the rotated tokens + expires_at."""
        session_row.access_token = tokens["access_token"]
        session_row.refresh_token = tokens["refresh_token"]
        expires_in = tokens.get("expires_in")
        if isinstance(expires_in, (int, float)):
            session_row.expires_at = datetime.now(UTC) + timedelta(
                seconds=int(expires_in)
            )
        db.add(session_row)
        await db.commit()
        await db.refresh(session_row)
        logger.info(
            "access_token_refreshed sub=%s session=%s...",
            session_row.sub,
            session_row.id[:8],
        )


# Module-level singleton — the proxy router imports a pre-built instance so
# the constructor's dependency wiring (settings + session_service) happens
# exactly once at app boot.
resource_server_client = ResourceServerClient(settings)


__all__ = [
    "ResourceServerClient",
    "RsSessionTerminated",
    "RsUnavailable",
    "resource_server_client",
]
