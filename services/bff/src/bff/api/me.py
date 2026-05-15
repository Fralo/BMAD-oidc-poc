"""GET /api/me — current-user identity endpoint (anonymous-only in Story 1.3).

For Story 1.3 this endpoint **always** returns 401 with the archetype error
envelope and ErrorCode `session_expired`, whether or not a session cookie is
present. The session table does not exist yet (Story 1.4 introduces it) and
the cookie-session OIDC plugin (Story 1.5) is what actually populates and
validates the cookie. This handler exists now so the SPA's authGuard
(Story 1.9) has a stable 401 contract to develop against.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from bff.core.errors import ErrorCode

router = APIRouter(tags=["Auth"])


@router.get("/api/me")
async def me() -> JSONResponse:
    return JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )
