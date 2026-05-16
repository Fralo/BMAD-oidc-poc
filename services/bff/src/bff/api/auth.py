"""`/auth/login`, `/auth/callback`, and `/auth/logout` — the BFF's OIDC
cookie-session entry/exit points (Stories 1.5 + 1.7).

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
6. On `POST /auth/logout`: revoke refresh token at Keycloak, call the
   end-session endpoint, delete the local `sessions` row, clear both the
   session and CSRF cookies, and return 204. Per architecture §A7, transport
   failures at Keycloak do NOT block local session teardown — the user
   perceives a successful logout even when the AS is unreachable.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bff.auth.keycloak_cookie_session import (
    OidcVerificationError,
    build_authorize_url,
    end_session,
    exchange_code,
    revoke_refresh_token,
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
# flow; the two reading-speed scopes are what the RS will enforce in Epic 3.
# `offline_access` was previously requested here on the mistaken belief that
# it was required for refresh tokens — refresh tokens come with the standard
# `authorization_code` grant. Requesting `offline_access` requires the user
# to hold the `offline_access` realm role (the seeded test users do not) and
# Keycloak rejects the token exchange with CODE_TO_TOKEN_ERROR
# "Offline tokens not allowed for the user or client". See D7 in
# deferred-work.md for the related "no offline session max lifespan" concern.
_AUTHORIZE_SCOPES: Final[tuple[str, ...]] = (
    "openid",
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


def _http_error_classifier(exc: httpx.HTTPError) -> str:
    """One-line classifier for upstream-failure WARN logs.

    Pure exception-type for transport errors (ConnectError, ReadTimeout,
    ...); type + status for HTTPStatusError so operators can distinguish
    401 (rotated client secret) from 429 (rate limit) from 5xx without
    leaking URL or response body.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTPStatusError({exc.response.status_code})"
    return type(exc).__name__


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


# ---------------------------------------------------------------------------
# /auth/logout (Story 1.7)
# ---------------------------------------------------------------------------


def _as_utc_aware(dt: datetime) -> datetime:
    """SQLite roundtrips strip tzinfo (Story 1.4 D31); reattach UTC when missing.

    Inlined here so the AC5 expired-session check matches `/api/me`'s shape
    without import gymnastics.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _clear_session_cookies(response: Response, cfg: AppSettings) -> None:
    """Clear `bff_session` AND `csrf_token` by setting them to empty with Max-Age=0.

    Mirrors the original `set_cookie` attributes (Story 1.5 Review Findings P3):
    `delete_cookie` omits `secure`/`samesite` args and breaks RFC 6265bis
    browsers under `BFF_SESSION_COOKIE_SECURE=True`. Both cookies share Path=/
    and SameSite=Lax; only the CSRF cookie omits HttpOnly (so the SPA can
    read it via `document.cookie` for the double-submit pattern).
    """
    response.set_cookie(
        key=cfg.bff_session_cookie_name,
        value="",
        max_age=0,
        httponly=True,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )
    response.set_cookie(
        key=cfg.bff_csrf_cookie_name,
        value="",
        max_age=0,
        httponly=False,
        samesite="lax",
        secure=cfg.bff_session_cookie_secure,
        path="/",
    )


def _session_expired_with_cookie_clear(cfg: AppSettings) -> JSONResponse:
    """Build the canonical 401 `session_expired` envelope AND clear both cookies.

    Used by `/auth/logout` for the missing/unknown/expired-session paths
    (AC5). Defensively clears the (now-useless) cookies even when there was
    no matching session row — leaves the browser in a clean unauthenticated
    state for a fresh login.
    """
    response = JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )
    _clear_session_cookies(response, cfg)
    return response


@router.post("/auth/logout", status_code=204)
async def auth_logout(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> Response:
    """Tear down the user's session — locally and at the AS — and return 204.

    Order matters (architecture §A7):
      1. revoke refresh_token at Keycloak  (best effort)
      2. call end_session_endpoint        (best effort)
      3. delete local `sessions` row       (always)
      4. clear `bff_session` + `csrf_token` cookies (always)
      5. return 204 No Content

    Steps 1 + 2 degrade honestly: any transport or HTTP failure is logged at
    WARN with a classifier (the exception type name) and the flow continues.
    The user perceives a successful logout even when Keycloak is unreachable
    — UX §J5 forbids half-logged-out states.
    """
    session_id = request.cookies.get(cfg.bff_session_cookie_name)
    if not session_id:
        logger.warning("auth_logout_missing_session_cookie")
        return _session_expired_with_cookie_clear(cfg)

    row = await _session_service.get_session(db, session_id=session_id)
    if row is None:
        logger.warning(
            "auth_logout_unknown_session session_id=%s",
            _safe_session_id_log(session_id),
        )
        return _session_expired_with_cookie_clear(cfg)

    if _as_utc_aware(row.expires_at) < datetime.now(UTC):
        # Lazy cleanup of the expired row; caller still gets 401.
        await _session_service.delete_expired_session(db, session_id=session_id)
        logger.warning(
            "auth_logout_expired_session session_id=%s",
            _safe_session_id_log(session_id),
        )
        return _session_expired_with_cookie_clear(cfg)

    logger.info(
        "auth_logout_start sub=%s session_id=%s",
        _safe_session_id_log(row.sub),
        _safe_session_id_log(session_id),
    )

    issuer = cfg.oidc_issuer_url.rstrip("/")
    revocation_url = f"{issuer}/protocol/openid-connect/revoke"
    end_session_url = f"{issuer}/protocol/openid-connect/logout"

    try:
        if row.refresh_token:
            try:
                await revoke_refresh_token(
                    refresh_token=row.refresh_token,
                    revocation_url=revocation_url,
                    client_id=cfg.oidc_client_id,
                    client_secret=cfg.bff_client_secret,
                )
            except httpx.HTTPError as exc:
                # Captures HTTPStatusError (from non-2xx — including 3xx)
                # AND transport subclasses (ConnectError, ReadTimeout,
                # ConnectTimeout). Local teardown still runs — A7 contract.
                logger.warning(
                    "auth_logout_revocation_failed: %s",
                    _http_error_classifier(exc),
                )
        else:
            # Row was created without a refresh_token (Story 1.5 stores
            # `str(token.get("refresh_token", ""))`). POSTing an empty
            # `token` would 400 at the AS and pollute the log with a
            # phantom "AS failure". Skip the call and log a real classifier.
            logger.info(
                "auth_logout_no_refresh_token session_id=%s",
                _safe_session_id_log(session_id),
            )

        if row.id_token:
            try:
                await end_session(
                    id_token=row.id_token,
                    end_session_url=end_session_url,
                    client_id=cfg.oidc_client_id,
                    client_secret=cfg.bff_client_secret,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "auth_logout_end_session_failed: %s",
                    _http_error_classifier(exc),
                )
        else:
            logger.info(
                "auth_logout_no_id_token session_id=%s",
                _safe_session_id_log(session_id),
            )
    finally:
        # UX §J5 invariant: tear down local state EVERY time, even on
        # client cancellation or unexpected upstream errors. shield() keeps
        # the DB commit uninterruptible if the task is being cancelled.
        try:
            await asyncio.shield(
                _session_service.delete_session(db, session_id=session_id)
            )
        except SQLAlchemyError as exc:
            # Without this guard, a DB failure here would crash the handler
            # AFTER upstream revocation succeeded — leaving the user
            # half-logged-out (cookies still in browser, row still in DB
            # if commit failed). Log ERROR and continue to cookie clear.
            logger.error("auth_logout_session_delete_failed: %s", type(exc).__name__)

    response = Response(status_code=204)
    _clear_session_cookies(response, cfg)
    logger.info(
        "auth_logout_complete sub=%s session_id=%s",
        _safe_session_id_log(row.sub),
        _safe_session_id_log(session_id),
    )
    return response
