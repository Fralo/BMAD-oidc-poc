"""GET /api/me — current-user identity endpoint.

Returns 200 with `{sub, preferred_username}` for a valid session cookie; 401
with the `session_expired` envelope for any of: missing cookie, unknown
session id, OR expired session. Expired sessions are deleted lazily on first
access (the response is still 401).

`preferred_username` is decoded from the stored id_token via PyJWT WITHOUT
signature verification — the token was already RS256-verified at
`/auth/callback` time (Story 1.5), so re-verifying per request would only
spend CPU and require a live JWKS connection. We trust our own DB.
"""

from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import ErrorCode
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


def _as_utc_aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@router.get("/api/me")
async def me(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> JSONResponse:
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        return _session_expired_response()

    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        return _session_expired_response()

    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        # Lazy cleanup of expired sessions on access. Caller still gets 401.
        await _session_service.delete_expired_session(db, session_id=session_id)
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
