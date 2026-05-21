"""GET /api/me — current-user identity endpoint.

Returns 200 with `{sub, preferred_username}` for a valid session cookie; 401
with the `session_expired` envelope for any of: missing cookie, unknown
session id, OR expired session. Expired sessions are deleted lazily on first
access (the response is still 401).

`preferred_username` is decoded from the stored id_token via PyJWT WITHOUT
signature verification — the token was already RS256-verified at
`/auth/callback` time (Story 1.5), so re-verifying per request would only
spend CPU and require a live JWKS connection. We trust our own DB.

Story 7.1 added two role-aware companion endpoints to demonstrate ACME-TS
principle P4 (separation of authN/authZ): `GET /api/me/roles` reads the
session's stored roles list; `GET /api/admin/ping` is a role-gated demo
that returns 200 only if the session carries the `admin` role.
"""

from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bff.auth.role_mapping import Role, deserialize_roles
from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import ErrorCode
from bff.models import entities
from bff.services.session_service import SessionService

router = APIRouter(tags=["Auth"])

_session_service = SessionService()


def _settings_dep() -> AppSettings:
    return settings


def _session_expired_response() -> JSONResponse:
    return JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )


def _forbidden_scope_response() -> JSONResponse:
    """Canonical 403 envelope for role-gated denials (Story 7.1)."""
    return JSONResponse(
        status_code=ErrorCode.FORBIDDEN_SCOPE.http_status,
        content={
            "errorCode": ErrorCode.FORBIDDEN_SCOPE.code,
            "message": ErrorCode.FORBIDDEN_SCOPE.message,
            "detail": None,
        },
    )


def _as_utc_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


async def _load_active_session(
    request: Request, db: AsyncSession, cfg: AppSettings
) -> entities.Session | None:
    """Return the active session row for the request, or None.

    Returning None covers all three failure modes the auth endpoints
    collapse into 401 `session_expired`: missing cookie, unknown row,
    expired row (with lazy delete). Centralizes the policy shared between
    `/api/me`, `/api/me/roles`, and `/api/admin/ping`.
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        return None
    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        return None
    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        await _session_service.delete_expired_session(db, session_id=session_id)
        return None
    return row


@router.get("/api/me")
async def me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    row = await _load_active_session(request, db, cfg)
    if row is None:
        return _session_expired_response()

    # Decode the stored id_token to surface `preferred_username`. Signature
    # verification was performed at /auth/callback; this is pure claim read.
    try:
        claims = jwt.decode(
            row.id_token,
            options={"verify_signature": False, "verify_exp": False},
        )
    except jwt.InvalidTokenError:
        # Defensive: a stored id_token that fails to parse implies DB corruption
        # or a bug at insert time. Treat as a missing session.
        return _session_expired_response()

    preferred_username = claims.get("preferred_username", "")
    return JSONResponse(
        status_code=200,
        content={"sub": row.sub, "preferred_username": preferred_username},
    )


@router.get("/api/me/roles")
async def me_roles(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    """Story 7.1: return the current session's mapped in-app roles.

    The role list is sourced from the `sessions.roles` column populated at
    /auth/callback time (Story 7.1 AC3). The wire shape is a JSON array of
    role-name strings sorted alphabetically — the stored blob is already
    sorted by `serialize_roles(...)`, so the deserialization preserves
    order without an extra sort.
    """
    row = await _load_active_session(request, db, cfg)
    if row is None:
        return _session_expired_response()
    return JSONResponse(
        status_code=200,
        content={"roles": deserialize_roles(row.roles)},
    )


@router.get("/api/admin/ping")
async def admin_ping(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    """Story 7.1: role-gated demo endpoint.

    The 401 (no session) check intentionally precedes the 403 (no role)
    check — an unauthenticated caller never sees the role failure mode and
    cannot probe whether `admin` is the gating role from outside an
    authenticated session.
    """
    row = await _load_active_session(request, db, cfg)
    if row is None:
        return _session_expired_response()
    if Role.ADMIN.value not in deserialize_roles(row.roles):
        return _forbidden_scope_response()
    return JSONResponse(status_code=200, content={"ok": True})
