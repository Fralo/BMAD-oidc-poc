"""`/auth/login` and `/auth/callback` — the BFF's OIDC cookie-session entry
points (Story 1.5).

Flow:

1. SPA navigates the user to `/auth/login?return_to=<path>`.
2. BFF mints a fresh `auth_states` row + PKCE verifier/challenge, signs the
   row id into a short-lived state-id cookie, and 302s to Keycloak's
   browser-facing `/authorize` URL with all the PKCE params.
3. Keycloak authenticates the user and 302s back to `/auth/callback?code=...&state=...`.
4. BFF validates the state-id cookie + the `state` query param + the
   `auth_states` row (deletion is atomic), exchanges `code + code_verifier`
   for tokens, verifies the id_token via JWKS, persists a `sessions` row,
   sets the session + csrf cookies, and 302s to `return_to`.
5. Any failure on the callback path returns 400 `auth_state_invalid` AND
   clears the state-id cookie.
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bff.auth.keycloak_cookie_session import (
    OidcVerificationError,
    build_authorize_url,
    exchange_code,
    sign_state_id,
    state_id_serializer,
    verify_id_token,
    verify_state_id,
)
from bff.auth.pkce import compute_code_challenge
from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import ErrorCode
from bff.services.session_service import SessionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"])

BFF_AUTH_STATE_COOKIE_NAME: Final[str] = "bff_auth_state"

# Scope set per architecture A1 + epics line 364. `openid` makes it an OIDC
# flow; `offline_access` ensures a refresh token; the two reading-speed
# scopes are what the RS will enforce in Epic 3.
_AUTHORIZE_SCOPES: Final[tuple[str, ...]] = (
    "openid",
    "offline_access",
    "reading-speed:read",
    "reading-speed:write",
)

# State-id cookie TTL must match `auth_states.expires_at` lifetime (5 min).
_STATE_COOKIE_MAX_AGE = 300

_session_service = SessionService()


def _settings_dep() -> AppSettings:
    return settings


def _safe_session_id_log(value: str | None) -> str:
    """Return first-8-chars of a session/cookie id, ellipsized. Never the full value."""
    if not value:
        return "(none)"
    return f"{value[:8]}..."


def _auth_state_invalid_response(
    state_cookie_name: str, *, secure: bool = False
) -> JSONResponse:
    """Build the canonical 400 envelope AND clear the state-id cookie.

    Uses set_cookie with max_age=0 (not delete_cookie) so the clearing header
    carries the same HttpOnly/SameSite attributes as the original set — required
    by RFC 6265bis browsers when BFF_SESSION_COOKIE_SECURE=True.
    """
    response = JSONResponse(
        status_code=ErrorCode.AUTH_STATE_INVALID.http_status,
        content={
            "errorCode": ErrorCode.AUTH_STATE_INVALID.code,
            "message": ErrorCode.AUTH_STATE_INVALID.message,
            "detail": None,
        },
    )
    response.set_cookie(
        key=state_cookie_name,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    return response


@router.get("/auth/login")
async def auth_login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
    return_to: str | None = None,
) -> RedirectResponse:
    """302 the browser to Keycloak's `/authorize` endpoint with PKCE."""
    row, code_verifier = await _session_service.create_auth_state(
        db, return_to=return_to
    )
    challenge = compute_code_challenge(code_verifier)
    serializer = state_id_serializer(cfg.bff_client_secret)
    signed_state_id = sign_state_id(serializer, row.id)

    redirect_url = build_authorize_url(
        authorize_url_browser=cfg.oidc_authorize_url_browser,
        redirect_uri=f"{cfg.bff_base_url}/auth/callback",
        client_id=cfg.oidc_client_id,
        scopes=_AUTHORIZE_SCOPES,
        state=row.state,
        nonce=row.nonce,
        code_challenge=challenge,
    )

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(
        key=BFF_AUTH_STATE_COOKIE_NAME,
        value=signed_state_id,
        max_age=_STATE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )
    logger.info(
        "auth_state_created id=%s return_to=%s",
        _safe_session_id_log(row.id),
        row.return_to,
    )
    _ = request  # currently unused; FastAPI provides it for future hooks (CSRF, etc.)
    return response


@router.get("/auth/callback", response_model=None)
async def auth_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse | JSONResponse:
    """Complete the PKCE handshake, persist a session, set cookies, 302 home."""

    # ---- 1) State + state-id cookie validation -----------------------------
    if not state:
        logger.warning("auth_callback_missing_state")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    serializer = state_id_serializer(cfg.bff_client_secret)
    cookie_value = request.cookies.get(BFF_AUTH_STATE_COOKIE_NAME)
    cookie_row_id = verify_state_id(
        serializer, cookie_value, max_age_seconds=_STATE_COOKIE_MAX_AGE
    )
    if cookie_row_id is None:
        logger.warning("auth_callback_state_cookie_invalid")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    row = await _session_service.consume_auth_state(db, state=state)
    if row is None:
        logger.warning("auth_callback_state_row_missing_or_expired")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    if row.id != cookie_row_id:
        # Tampered query/state pair — state matched a real row, but the
        # signed cookie pointed at a different one. The row is already
        # consumed (deleted) which prevents replay.
        logger.warning("auth_callback_cookie_row_id_mismatch")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    # ---- 2) Token exchange + id_token verification -------------------------
    if not code:
        logger.warning("auth_callback_missing_code")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    token_url = cfg.oidc_issuer_url.rstrip("/") + "/protocol/openid-connect/token"
    try:
        token = await exchange_code(
            code=code,
            code_verifier=row.code_verifier,
            redirect_uri=f"{cfg.bff_base_url}/auth/callback",
            token_url=token_url,
            client_id=cfg.oidc_client_id,
            client_secret=cfg.bff_client_secret,
        )
    except OidcVerificationError as exc:
        logger.warning("auth_callback_token_exchange_failed: %s", exc)
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    id_token_jwt = token.get("id_token")
    if not isinstance(id_token_jwt, str):
        logger.warning("auth_callback_id_token_missing")
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    try:
        claims = verify_id_token(
            id_token=id_token_jwt,
            jwks_url=cfg.oidc_jwks_url,
            # D2/D8 caveat: Keycloak emits `iss=KC_HOSTNAME` (the browser-facing
            # URL) in id_tokens. Use the browser-facing URL here, not the
            # back-channel `oidc_issuer_url`.
            expected_issuer=cfg.oidc_authorize_url_browser,
            expected_audience=cfg.oidc_client_id,
            expected_nonce=row.nonce,
        )
    except OidcVerificationError as exc:
        logger.warning("auth_callback_id_token_invalid: %s", exc)
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    sub = claims["sub"]
    try:
        expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    except (ValueError, OSError) as exc:
        logger.warning("auth_callback_exp_invalid: %s", exc)
        return _auth_state_invalid_response(
            BFF_AUTH_STATE_COOKIE_NAME, secure=cfg.bff_session_cookie_secure
        )

    # ---- 3) Persist session + set cookies + redirect ----------------------
    session_row = await _session_service.create_session(
        db,
        sub=sub,
        access_token=str(token.get("access_token", "")),
        refresh_token=str(token.get("refresh_token", "")),
        id_token=id_token_jwt,
        expires_at=expires_at,
    )

    redirect = RedirectResponse(url=row.return_to or "/", status_code=302)
    # Clear the now-consumed state-id cookie with matching attributes.
    redirect.set_cookie(
        key=BFF_AUTH_STATE_COOKIE_NAME,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )
    # Set the session cookie — HttpOnly, opaque value, server-side TTL via row.
    redirect.set_cookie(
        key=cfg.bff_session_cookie_name,
        value=session_row.id,
        httponly=True,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )
    # Set the CSRF cookie — non-HttpOnly so the SPA's csrfInterceptor can read it.
    redirect.set_cookie(
        key=cfg.bff_csrf_cookie_name,
        value=session_row.csrf_secret,
        httponly=False,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )
    logger.info(
        "auth_callback_success sub=%s session_id=%s return_to=%s",
        _safe_session_id_log(sub),
        _safe_session_id_log(session_row.id),
        row.return_to,
    )
    return redirect
