"""E2E-profile-only `POST /v1/test/reset` endpoint (Story 1.12).

Purpose
-------
Provides a guarded test-reset surface for Playwright E2E specs (Story 1.11
and beyond): a single POST that truncates the BFF's auth-related tables
(`sessions`, `auth_states`) and returns 204. Each E2E test starts from a
known clean state without per-test ordering hacks.

Gating (defense-in-depth)
-------------------------
The route is only mounted when BOTH of the following hold at app build
time:
  - `ENABLE_TEST_RESET=true` (`cfg.enable_test_reset is True`)
  - `TEST_RESET_TOKEN` is a non-empty, non-whitespace-only string

When either gate is off, `register_test_reset_router` is a no-op and any
HTTP method against `/v1/test/reset` falls through to FastAPI's default
404 envelope. Production builds (default compose profile) leave the gate
off; the `e2e` compose profile turns it on with a required token.

Authentication
--------------
A shared bearer token sent via `Authorization: Bearer <token>` is the
sole auth mechanism. Comparison is constant-time via `hmac.compare_digest`
to avoid timing-oracle leaks (mirrors `bff/auth/csrf.py:58-60`). All
auth-failure paths emit the project's `session_expired` envelope (the
same the BFF emits for unauthenticated `/api/me`) so the endpoint does
not leak existence via a unique error code.

Safety notes
------------
- This module is registered conditionally; production builds omit the
  route entirely. Bearer-token leakage in an `ENABLE_TEST_RESET=true`
  deployment IS a real risk and is documented in PRD §4 "out of scope".
- CSRF is bypassed for `/v1/test/reset` (see
  `bff/auth/csrf.py::_CSRF_EXEMPT_PATHS`) because the Playwright fixture
  authenticates via the bearer header alone — there is no browser
  session cookie in play.
- No `Set-Cookie` headers are emitted (no session state to clear).
- No rate limiting (out of scope per Story 1.12 Dev Notes).

References
----------
- epics.md §Story 1.12 (lines 666–704)
- architecture.md §"POST /v1/test/reset (e2e profile only)" (lines 1354–1360)
- AR32 (epics line 97): test-reset endpoint architectural requirement
- Story 1.4 (sessions/auth_states tables); Story 1.5 (session_service
  truncate idiom); Story 1.6 (CSRF middleware exemption is added there);
  Story 1.7 (Response(status_code=204) pattern).
"""

import hmac
import logging
from typing import Annotated, Final

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete as _delete
from sqlalchemy.ext.asyncio import AsyncSession

from bff.core.config import AppSettings, settings
from bff.core.database import get_session
from bff.core.errors import ErrorCode
from bff.models import entities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Test Reset"])

# The full path the route is mounted at. Kept as a module-level constant
# so tests and the CSRF exemption can reference the exact same string.
_TEST_RESET_PATH: Final[str] = "/v1/test/reset"
_BEARER_PREFIX: Final[str] = "Bearer "

__all__ = ["register_test_reset_router", "router"]


def _settings_dep() -> AppSettings:
    """Singleton settings dependency — mirrors `api/me.py::_settings_dep`."""
    return settings


def _unauthorized_response() -> JSONResponse:
    """401 envelope reused from `/api/me`'s missing-session response.

    The wire-level errorCode is `session_expired` (lower_snake_case per
    architecture §C5). REUSING this code — rather than adding a fresh
    `INVALID_TEST_RESET_BEARER` — is intentional: a unique code would
    leak that the endpoint exists to an attacker probing for it.
    """
    return JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )


def _classify_auth_failure(auth_header: str | None) -> str | None:
    """Classify an `Authorization` header into a failure tag, or `None`.

    Returns `None` when the header is a well-formed `Bearer <token>` with
    a non-empty single-token payload — the caller then performs the
    constant-time value comparison.

    Returns one of:
      - "missing_header" — header absent OR present but empty/whitespace.
      - "wrong_scheme"   — present and non-empty but does NOT start with
                           `Bearer ` (case-sensitive — RFC 6750 §2.1 says
                           the scheme is case-insensitive, but the
                           project's convention is exact-match, mirroring
                           the CSRF middleware's literal-string checks).
      - "empty_token"    — `Bearer ` with nothing (or only whitespace)
                           after.
      - None             — caller validates the token value.

    Note: a `Bearer foo bar` header (multiple whitespace-separated tokens)
    is NOT classified here; it survives this function with classification
    `None` and is rejected at the constant-time-compare step as
    `token_mismatch` (the entire `"foo bar"` substring is the candidate
    token and almost certainly will not match the env-supplied value).
    """
    if auth_header is None or auth_header.strip() == "":
        return "missing_header"
    if not auth_header.startswith(_BEARER_PREFIX):
        return "wrong_scheme"
    candidate = auth_header[len(_BEARER_PREFIX) :]
    if candidate.strip() == "":
        return "empty_token"
    return None


@router.post("/test/reset", status_code=204)
async def test_reset(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> Response:
    """Truncate `sessions` and `auth_states`; return 204.

    Bearer-token guarded. Auth failures emit the `session_expired` 401
    envelope (no enumeration leak via a distinct error code). On success,
    the response body is empty (Story 1.7's `Response(status_code=204)`
    idiom). The truncate sequence is two bare `DELETE FROM <table>`
    statements followed by a single commit (atomic from the DB's POV).

    Story 2.3 will extend this handler with a third DELETE for the
    `books` table; keep the structure ordered and explicit (one
    `await db.execute(...)` per table) so that addition is a one-line
    insertion rather than a refactor.
    """
    auth_header = request.headers.get("authorization")
    classification = _classify_auth_failure(auth_header)
    if classification is not None or auth_header is None:
        # Never log the bearer string itself — only the classifier tag.
        # Architecture §Logging conventions: token material is forbidden
        # from any log line. The `auth_header is None` half is a
        # belt-and-braces type narrow for `ty`; the classifier already
        # returns "missing_header" in that case.
        logger.warning(
            "test_reset_unauthorized: %s", classification or "missing_header"
        )
        return _unauthorized_response()

    # The classifier guarantees the prefix and the non-None header.
    provided = auth_header[len(_BEARER_PREFIX) :]
    expected = cfg.test_reset_token
    # hmac.compare_digest with byte arguments of unequal length returns
    # False without leaking byte-wise differences. The length itself is
    # observable (one bit of leakage) — acceptable for a shared bearer
    # whose length is operator-set and not user-supplied.
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("test_reset_unauthorized: token_mismatch")
        return _unauthorized_response()

    # Happy path. `synchronize_session=False` skips the ORM in-memory
    # evaluator step — Story 1.4's D31 mitigation for SQLite naive-datetime
    # mismatches; harmless here because the truncate has no WHERE clause.
    # The pattern mirrors `SessionService.delete_session` (session_service.py:226).
    sessions_result = await db.execute(
        _delete(entities.Session),
        execution_options={"synchronize_session": False},
    )
    auth_states_result = await db.execute(
        _delete(entities.AuthState),
        execution_options={"synchronize_session": False},
    )
    await db.commit()

    # SQLAlchemy `Result` from a `DELETE` execution is in fact a
    # `CursorResult` that exposes `.rowcount`. The static signature of
    # `AsyncSession.execute` is the broader `Result[Any]`, hence the
    # `getattr` form — keeps `ty` happy without dragging
    # `sqlalchemy.engine.CursorResult` into the import surface.
    sessions_deleted = getattr(sessions_result, "rowcount", -1)
    auth_states_deleted = getattr(auth_states_result, "rowcount", -1)
    logger.info(
        "test_reset_truncated tables=sessions,auth_states "
        "sessions_deleted=%s auth_states_deleted=%s",
        sessions_deleted,
        auth_states_deleted,
    )
    return Response(status_code=204)


def register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None:
    """Conditionally mount the test-reset route.

    Registers the router on `app` only when BOTH of the following hold:
      - `cfg.enable_test_reset is True`
      - `cfg.test_reset_token` is non-empty after `.strip()`

    Either gate failing makes this a no-op; the request to
    `/v1/test/reset` then falls through to FastAPI's default 404. The
    second gate (empty/whitespace-only token) is defense-in-depth: an
    operator who toggles the env flag but forgets the token gets the
    same behavior as gate-off, plus a WARN log entry surfacing the
    misconfiguration.

    Emits one INFO line `test_reset_route_registered` on success so an
    operator inspecting startup logs can confirm the gate fired.
    """
    if not cfg.enable_test_reset:
        return
    if not cfg.test_reset_token.strip():
        # Defense-in-depth: an enabled gate with an empty token is a
        # misconfiguration, not a silent "no auth" exposure. Treat as
        # gate-off and surface the cause in logs.
        logger.warning("test_reset_route_skipped reason=test_reset_token_empty")
        return
    app.include_router(router)
    logger.info("test_reset_route_registered path=%s", _TEST_RESET_PATH)
