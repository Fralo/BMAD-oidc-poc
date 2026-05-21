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

``compute_estimate`` (Story 4.2) is the third public method on this
class. It brokers ``POST /v1/estimate`` and reuses the same
refresh-and-replay cycle as the reading-speed methods.

References
----------
- epics.md §Story 3.5 lines 1326-1373
- epics.md §Story 4.2 lines 1585-1628
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

from bff.aop.auth_logging import AuthDecision, emit_auth_decision
from bff.core.config import AppSettings, settings
from bff.models.entities.session import Session
from bff.services.session_service import SessionService

logger = logging.getLogger(__name__)

# AR19 / architecture §C6 — 5s connect, 10s read; zero retries on 5xx.
# Mirrored on the Keycloak `/token` refresh call (same upstream budget per
# architecture §C6's BFF→Keycloak row).
_RS_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0)
_READING_SPEED_PATH = "/v1/reading-speed"
_ESTIMATE_PATH = "/v1/estimate"


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


# CR3 / CR4: Reasonable upper bound on ``expires_in`` so a malformed /
# malicious refresh response cannot OverflowError on ``timedelta(seconds=...)``
# or produce a session that "expires" past year 9999. 10 years in seconds —
# any legitimate Keycloak refresh-grant response is several orders of
# magnitude under this.
_MAX_REASONABLE_EXPIRES_IN_SEC: int = 10 * 365 * 24 * 60 * 60


def _is_valid_expires_in(value: object) -> bool:
    """True when ``value`` is a bounded positive numeric usable for timedelta.

    Rejects None, strings, bool (``True is 1`` would otherwise pass),
    negative / zero, NaN / inf, and absurdly large values. The caller
    surfaces a False result as ``_RefreshFailed("malformed_response")`` so
    the cookie-clearing 401 path fires explicitly rather than silently
    leaving ``expires_at`` stale.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if value != value or value in (float("inf"), float("-inf")):  # NaN / inf
        return False
    if value <= 0:
        return False
    return value <= _MAX_REASONABLE_EXPIRES_IN_SEC


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
        *,
        default_token_url: str = "",
    ) -> None:
        # Story 7.2: ``default_token_url`` is a test-only convenience that lets
        # fixtures construct a client without threading ``token_url`` through
        # every call. Production routes always pass an explicit ``token_url``
        # from ``discovery.token_endpoint`` — the default stays empty.
        self._settings = settings_obj
        self._session_service = session_service or SessionService()
        self._default_token_url = default_token_url

    async def get_reading_speed(
        self,
        db: AsyncSession,
        session_row: Session,
        *,
        token_url: str = "",
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``GET /v1/reading-speed`` with refresh-and-replay.

        Returns ``(http_status, parsed_json_body_or_None)``. Raises
        :class:`RsUnavailable` on transport failure or RS 5xx;
        :class:`RsSessionTerminated` when the refresh cycle cannot
        recover. ``token_url`` is the OIDC token endpoint used by the
        refresh-grant POST — comes from `discovery.token_endpoint`
        (Story 7.2).
        """
        return await self._call_with_refresh(
            db,
            session_row,
            method="GET",
            path=_READING_SPEED_PATH,
            body=None,
            token_url=token_url,
        )

    async def put_reading_speed(
        self,
        db: AsyncSession,
        session_row: Session,
        payload: dict[str, Any],
        *,
        token_url: str = "",
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``PUT /v1/reading-speed`` with the JSON ``payload``.

        Same return / raise contract as :meth:`get_reading_speed`. The
        ``payload`` is forwarded verbatim — NO ``sub`` injection per
        NFR6.
        """
        return await self._call_with_refresh(
            db,
            session_row,
            method="PUT",
            path=_READING_SPEED_PATH,
            body=payload,
            token_url=token_url,
        )

    async def compute_estimate(
        self,
        db: AsyncSession,
        session_row: Session,
        *,
        pages: int,
        token_url: str = "",
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue ``POST /v1/estimate`` with body ``{"pages": pages}``.

        Same return / raise contract as :meth:`get_reading_speed`. NFR6:
        ``sub`` is NEVER added to the URL, query, or body. The RS reads
        ``sub`` from the JWT only (architecture line 1141).
        """
        return await self._call_with_refresh(
            db,
            session_row,
            method="POST",
            path=_ESTIMATE_PATH,
            body={"pages": pages},
            token_url=token_url,
        )

    async def _call_with_refresh(
        self,
        db: AsyncSession,
        session_row: Session,
        *,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        token_url: str,
    ) -> tuple[int, dict[str, Any] | None]:
        effective_token_url = token_url or self._default_token_url
        if not effective_token_url:
            msg = (
                "ResourceServerClient.token_url is required — pass token_url="
                "discovery.token_endpoint from the route handler or set "
                "default_token_url on the test fixture."
            )
            raise ValueError(msg)
        # First attempt with the current access_token.
        status, parsed = await self._do_rs_call(
            method, path, session_row.access_token, body
        )
        if status != 401:
            return status, parsed

        # RS-401 → attempt refresh-and-replay (single cycle per AR19 / A6).
        try:
            new_tokens = await self._refresh_access_token(
                session_row, effective_token_url
            )
        except _RefreshFailed as exc:
            # Refresh itself failed — clear session row + emit cookie-clearing 401.
            # ACME schema is a tight 4-field shape; the `cause` classifier is
            # dropped from the wire by design.
            emit_auth_decision(
                decision=AuthDecision.DENY,
                reason="refresh_failed",
                sub=session_row.sub,
            )
            await self._session_service.delete_session(db, session_id=session_row.id)
            raise RsSessionTerminated(clear_cookies=True) from exc

        # Persist the rotated tokens BEFORE the retry so a crash mid-retry
        # leaves the session in a forward-only state (next request will use
        # the fresh access_token).
        await self._persist_refreshed_tokens(db, session_row, new_tokens)

        retry_status, retry_parsed = await self._do_rs_call(
            method, path, new_tokens["access_token"], body
        )
        if retry_status == 401:
            # Retry still 401 — refresh worked but RS still rejected.
            # AC4 case 5: leave session in place; emit 401 without
            # clearing cookies. The SPA's /login redirect produces a new
            # login that overwrites the session on success.
            emit_auth_decision(
                decision=AuthDecision.DENY,
                reason="rs_401_after_refresh",
                sub=session_row.sub,
            )
            raise RsSessionTerminated(clear_cookies=False)
        return retry_status, retry_parsed

    async def _do_rs_call(
        self,
        method: str,
        path: str,
        access_token: str,
        body: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any] | None]:
        """Issue a single RS HTTP call. Normalize failures to RsUnavailable."""
        url = self._settings.rs_base_url.rstrip("/") + path
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=_RS_TIMEOUT) as client:
                if method == "GET":
                    response = await client.get(url, headers=headers)
                elif method == "PUT":
                    response = await client.put(url, headers=headers, json=body)
                elif method == "POST":
                    response = await client.post(url, headers=headers, json=body)
                else:  # pragma: no cover -- only GET/PUT/POST shapes are wired
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

        # An empty body is malformed for every RS endpoint we wire EXCEPT
        # 401: OAuth 2.0 / RFC 6750 challenges legitimately omit a body, and
        # the refresh-and-replay logic in ``_call_with_refresh`` consumes
        # the bare (401, None) tuple. For 2xx / 412 / 403 / 422 the contract
        # always carries either the success payload or the typed error
        # envelope, so an empty body there is treated the same way CR10
        # treats a non-dict 2xx body — an honest FR-ERROR-01 503 so the SPA
        # never sees a JSON ``null`` from us.
        if not response.content:
            if response.status_code == 401:
                return response.status_code, None
            logger.warning(
                "resource_server_unavailable cause=rs_empty_body http_status=%s",
                response.status_code,
            )
            raise RsUnavailable("rs_empty_body", http_status=response.status_code)
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        if not isinstance(parsed, dict) and parsed is not None:
            # CR10: The RS contract emits dicts; a list or scalar 2xx body
            # is a contract regression. Previously we forwarded
            # ``(status, None)`` which surfaced to the SPA as a 200 with the
            # JSON literal ``null`` — calling ``.pages_per_hour`` on null
            # threw a ``TypeError`` that classified as ``{kind: 'unknown'}``
            # and rendered no error message. Treat a malformed 2xx body the
            # same as a 5xx — honest FR-ERROR-01 failure so UX-DR12 copy
            # fires.
            if response.status_code < 400:
                logger.warning(
                    "resource_server_unavailable cause=rs_malformed_body "
                    "http_status=%s parsed_type=%s",
                    response.status_code,
                    type(parsed).__name__,
                )
                raise RsUnavailable(
                    "rs_malformed_body", http_status=response.status_code
                )
            parsed = None
        return response.status_code, parsed

    async def _refresh_access_token(
        self, session_row: Session, token_url: str
    ) -> dict[str, Any]:
        """Exchange refresh_token for a new access_token at Keycloak.

        Mirrors the BFF's existing ``keycloak_cookie_session.exchange_code``
        timeout idiom (Story 1.5). Uses a plain httpx POST with form-encoded
        body — Keycloak's confidential-client refresh grant accepts
        ``client_id`` and ``client_secret`` as form fields. Story 7.2:
        ``token_url`` comes from `discovery.token_endpoint`, threaded
        through `_call_with_refresh` from the per-request handler.

        Raises ``_RefreshFailed`` on any failure mode. The caller surfaces
        this as ``RsSessionTerminated(clear_cookies=True)``.
        """
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
        # CR3 / CR4: ``expires_in`` MUST be present and convertible to a
        # bounded integer. If absent (some IdP edge configs) or invalid,
        # ``_persist_refreshed_tokens`` would leave the stored ``expires_at``
        # at its pre-refresh value — almost certainly already in the past —
        # so the very next request's ``_require_session`` check would tear
        # the just-refreshed session down. Treat the case as a refresh
        # failure so the cookie-clearing 401 path fires explicitly instead
        # of producing a silent boot-the-user-out-on-next-request.
        if not _is_valid_expires_in(payload.get("expires_in")):
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
        # _is_valid_expires_in (called in _refresh_access_token) has already
        # confirmed the value is a bounded int/float; the int() coercion
        # here cannot OverflowError.
        session_row.expires_at = datetime.now(UTC) + timedelta(
            seconds=int(tokens["expires_in"])
        )
        db.add(session_row)
        await db.commit()
        await db.refresh(session_row)
        emit_auth_decision(
            decision=AuthDecision.REFRESH,
            reason="access_token_refreshed",
            sub=session_row.sub,
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
