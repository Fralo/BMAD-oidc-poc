"""BFF proxy for ``/v1/reading-speed`` → Resource Server (Story 3.5).

Thin pass-through proxy:

* Session check mirrors ``api/me.py:50-69`` — missing cookie / unknown id /
  expired row each yield ``401 session_expired`` (the standard envelope via
  ``app_exception_handler``).
* GET is CSRF-exempt (safe method); PUT enforces CSRF via the existing
  middleware — no exemption is added.
* The body is forwarded verbatim for 2xx / 4xx responses from the RS; the
  proxy does NOT re-wrap errorCodes (412 ``reading_speed_unset`` / 403
  ``forbidden_scope`` / 422 ``invalid_input`` flow through unchanged).
* RS 5xx and transport failures map to a project-owned ``503
  resource_server_unavailable`` envelope per FR-ERROR-01 / AR17.
* The refresh-and-replay cycle (NFR3 / architecture §A6) is owned by
  :class:`ResourceServerClient` — the router never sees the cycle; it
  receives the final ``(status, body)``. When the cycle cannot recover the
  router emits ``401 session_expired`` (with cookies cleared if refresh
  itself failed; without if refresh worked but the retry still 401'd).

References
----------
- epics.md §Story 3.5 lines 1333-1373
- architecture.md §C2 lines 376-378 (BFF endpoint contract)
- services/bff/src/bff/api/me.py:50-69 (the session-check pattern mirrored
  here)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import AppException, ErrorCode
from bff.models.entities.session import Session as SessionRow
from bff.services.resource_server_client import (
    RsSessionTerminated,
    RsUnavailable,
    resource_server_client,
)
from bff.services.session_service import SessionService

router = APIRouter(tags=["reading-speed"])

_session_service = SessionService()


def _settings_dep() -> AppSettings:
    return settings


def _as_utc_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _require_session(
    request: Request, db: AsyncSession, cfg: AppSettings
) -> SessionRow:
    """Resolve the session row for the current request or raise 401.

    Mirrors ``api/me.py:50-69``. Three failure modes — missing cookie,
    unknown id, expired row — all yield ``AppException(SESSION_EXPIRED)``;
    the existing ``app_exception_handler`` maps that to the standard
    envelope at 401. Expired rows are lazily deleted (same as me.py).
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        raise AppException(ErrorCode.SESSION_EXPIRED)
    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        await _session_service.delete_expired_session(db, session_id=session_id)
        raise AppException(ErrorCode.SESSION_EXPIRED)
    return row


def _session_terminated_response(
    cfg: AppSettings, *, clear_cookies: bool
) -> JSONResponse:
    """Emit a 401 ``session_expired`` response, optionally with cookies cleared.

    ``clear_cookies=True`` is the refresh-failure path (AC4 case 4): the
    sessions row has already been deleted by ``ResourceServerClient``;
    the response clears both the session cookie and ``csrf_token`` cookie
    via ``Max-Age=0`` so the browser drops them. ``clear_cookies=False``
    is the refresh-worked-but-retry-still-401 path (AC4 case 5): the
    session stays in place; the SPA's redirect to ``/login`` will produce
    a fresh login.
    """
    response = JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )
    if clear_cookies:
        response.delete_cookie(cfg.bff_session_cookie_name, path="/")
        response.delete_cookie(cfg.bff_csrf_cookie_name, path="/")
    return response


def _resource_server_unavailable_response() -> JSONResponse:
    """Emit the project-standard 503 ``resource_server_unavailable`` envelope."""
    return JSONResponse(
        status_code=ErrorCode.RESOURCE_SERVER_UNAVAILABLE.http_status,
        content={
            "errorCode": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.code,
            "message": ErrorCode.RESOURCE_SERVER_UNAVAILABLE.message,
            "detail": None,
        },
    )


@router.get("/reading-speed")
async def get_reading_speed(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    session_row = await _require_session(request, db, cfg)
    try:
        status, body = await resource_server_client.get_reading_speed(db, session_row)
    except RsSessionTerminated as exc:
        return _session_terminated_response(cfg, clear_cookies=exc.clear_cookies)
    except RsUnavailable:
        # WARN log emitted inside ResourceServerClient; here we only build
        # the standard 503 envelope (no need to re-log).
        return _resource_server_unavailable_response()
    return JSONResponse(status_code=status, content=body)


@router.put("/reading-speed")
async def put_reading_speed(
    request: Request,
    payload: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    session_row = await _require_session(request, db, cfg)
    try:
        status, body = await resource_server_client.put_reading_speed(
            db, session_row, payload
        )
    except RsSessionTerminated as exc:
        return _session_terminated_response(cfg, clear_cookies=exc.clear_cookies)
    except RsUnavailable:
        return _resource_server_unavailable_response()
    return JSONResponse(status_code=status, content=body)
