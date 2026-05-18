"""e2e profile test-reset endpoint for the Resource Server.

Purpose
-------
Exposes ``POST /v1/test/reset``: a guarded route that truncates the
``reading_speeds`` table so the Playwright J4 / J3 / J6 specs can rely on
a deterministic empty reading-speed state between tests.

Gating
------
The route is registered ONLY when ALL THREE gates pass:

1. ``ENABLE_TEST_RESET=true`` (pydantic-settings coerces ``"true"`` /
   ``"True"`` / ``"1"`` / ``"yes"`` / ``"on"`` to ``True``).
2. ``TEST_RESET_TOKEN`` is non-empty after ``.strip()``.
3. ``TEST_RESET_TOKEN.strip() != "change-me"`` — the archetype default
   in the repo-root ``.env.example`` ships as ``"change-me"``;
   accepting that as a real token would let a misconfigured production
   stack be hosed by anyone reading the public template. This is the
   RS-specific defense-in-depth step on top of the BFF Story 1.12 gate.

When any gate fails, ``register_test_reset_router`` is a no-op: the route
is not mounted, ``/v1/test/reset`` returns FastAPI's standard
``{"detail": "Not Found"}`` 404 envelope on every method, and the env
vars are inert.

Safety
------
- Production builds (the ``default`` compose profile) leave the gate off.
- The handler authenticates via a constant-time compare against the env
  token, NOT via the JWT path. ``oidc_bearer.get_authenticated_principal``
  is intentionally NOT a dependency on this route — attaching a JWT to a
  test-reset request is ignored (the route does not consult JWT material
  at all).
- The bearer string is NEVER logged. Auth-failure paths log only a fixed
  classifier (``missing_header`` / ``wrong_scheme`` / ``empty_token`` /
  ``token_mismatch``).
- All auth-failure paths emit the SAME 401 envelope
  (``errorCode: "session_expired"``) — no enumeration leak in ``detail``.

References
----------
- epics.md §"Story 3.4: RS — POST /v1/test/reset endpoint" lines 1282-1314.
- architecture.md §"POST /v1/test/reset (e2e profile only)" lines 1354-1360.
- services/bff/src/bff/api/test_reset.py — the BFF analog (Story 1.12);
  the two endpoints share NO code per architecture §I3, but the gating
  + bearer-check pattern is reused (with the extra placeholder-reject).
"""

from __future__ import annotations

import hmac
import logging
from typing import Annotated, Final

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import delete as _delete
from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.core.config import AppSettings, settings
from resource_server.core.database import get_session
from resource_server.core.errors import ErrorCode
from resource_server.models.entities.reading_speed import ReadingSpeed

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["Test Reset"])

_TEST_RESET_PATH: Final[str] = "/v1/test/reset"
_BEARER_PREFIX: Final[str] = "Bearer "

# Set of normalized placeholder tokens that we reject at registration time.
# Normalization (case-fold + underscore→hyphen) catches operator typos like
# ``Change-Me`` / ``CHANGE-ME`` / ``change_me`` / ``changeme`` that would
# otherwise bypass the placeholder-reject defense-in-depth check. CR3 from
# code review.
_PLACEHOLDER_TOKENS: Final[frozenset[str]] = frozenset({"change-me", "changeme"})


def _is_placeholder(stripped_token: str) -> bool:
    """Return True if the (already-stripped) token matches a known placeholder.

    Normalizes case + ``_``→``-`` before comparing so trivial typos still
    trip the gate.
    """
    normalized = stripped_token.lower().replace("_", "-")
    return normalized in _PLACEHOLDER_TOKENS


__all__ = ["register_test_reset_router", "router"]


def _settings_dep() -> AppSettings:
    """Resolve ``AppSettings`` for the handler.

    Indirected through this helper so the test suite can override via
    ``app.dependency_overrides[_settings_dep] = lambda: AppSettings(...)``
    without monkeypatching the module-level singleton.
    """
    return settings


def _unauthorized_response() -> JSONResponse:
    """Return the canonical 401 envelope used by every auth-failure path.

    Returns ``JSONResponse`` directly (rather than raising
    ``AppException(ErrorCode.SESSION_EXPIRED)`` and letting the existing
    ``app_exception_handler`` build the body) so the WARN log and the
    response emission stay in one explicit place — the route's auth is
    bespoke and does not flow through the JWT-validation machinery.
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
    """Return a classifier string if the ``Authorization`` header is malformed.

    Returns ``None`` when the header parses to a non-empty bearer token —
    the caller then compares the token bytes against the env value.

    Classifier values:
        - ``"missing_header"``: header absent OR empty / whitespace-only.
        - ``"wrong_scheme"``: header present but does not start with the
          literal prefix ``"Bearer "`` (case-sensitive — accepted
          simplification of RFC 6750 §2.1 per BFF Story 1.12 convention).
        - ``"empty_token"``: header is exactly ``"Bearer"`` followed by
          whitespace and nothing else.

    "Bearer foo bar" returns ``None`` — the scheme is correct and the
    post-prefix content ``"foo bar"`` is a bearer-token-shaped string
    that simply will not match the env value. The caller's
    constant-time compare classifies it as ``token_mismatch``.
    """
    if auth_header is None or auth_header.strip() == "":
        return "missing_header"
    if not auth_header.startswith(_BEARER_PREFIX):
        return "wrong_scheme"
    token = auth_header[len(_BEARER_PREFIX) :]
    if token.strip() == "":
        return "empty_token"
    return None


@router.post(
    "/test/reset",
    status_code=204,
    responses={
        # CR2: declare the 401 envelope on the OpenAPI surface so generated
        # SDK clients / contract tests see the full response shape, not just
        # the happy-path 204. Every auth-failure mode the handler returns
        # uses this exact body.
        401: {
            "description": "Bearer authentication required (env-bearer).",
            "content": {
                "application/json": {
                    "example": {
                        "errorCode": "session_expired",
                        "message": "Authentication required",
                        "detail": None,
                    }
                }
            },
        },
    },
)
async def test_reset(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cfg: Annotated[AppSettings, Depends(_settings_dep)],
) -> Response:
    """Truncate ``reading_speeds`` when the env-bearer authenticates."""
    auth_header = request.headers.get("authorization")
    classification = _classify_auth_failure(auth_header)
    if classification is not None:
        logger.warning("test_reset_unauthorized: %s", classification)
        return _unauthorized_response()
    # auth_header is guaranteed to start with "Bearer " (and have a
    # non-empty token after the prefix) per _classify_auth_failure.
    assert auth_header is not None  # noqa: S101 -- ty narrowing hint
    provided = auth_header[len(_BEARER_PREFIX) :]
    expected = cfg.test_reset_token
    if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
        logger.warning("test_reset_unauthorized: token_mismatch")
        return _unauthorized_response()

    # Happy path: truncate reading_speeds; single commit.
    result = await db.execute(
        _delete(ReadingSpeed),
        execution_options={"synchronize_session": False},
    )
    await db.commit()
    deleted = getattr(result, "rowcount", -1)
    logger.info(
        "test_reset_truncated tables=reading_speeds reading_speeds_deleted=%s",
        deleted,
    )
    return Response(status_code=204)


def register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None:
    """Conditionally mount ``POST /v1/test/reset`` on ``app``.

    The three gates (env-flag, non-empty token, non-placeholder token)
    are evaluated here so the route is invisible — even from OpenAPI —
    on production builds. WARN logs differentiate the three skip
    classifiers so an operator inspecting startup logs can see why the
    route was omitted.
    """
    if not cfg.enable_test_reset:
        return
    raw = cfg.test_reset_token
    stripped = raw.strip()
    if not stripped:
        # Defense-in-depth: empty / whitespace-only token == "not configured".
        logger.warning("test_reset_route_skipped reason=test_reset_token_empty")
        return
    if _is_placeholder(stripped):
        # Defense-in-depth: archetype default in .env.example is "change-me";
        # a real production stack must rotate this before enabling the gate.
        # CR3: case-insensitive + ``_``→``-`` normalized so trivial typos
        # (``Change-Me``, ``CHANGE-ME``, ``change_me``) still trip the gate.
        logger.warning(
            "test_reset_route_skipped reason=test_reset_token_default_placeholder"
        )
        return
    if raw != stripped:
        # CR1: gate uses the stripped form but the runtime bearer compare
        # uses the RAW env value. If the operator's env has surrounding
        # whitespace, the route mounts but every legitimate request fails.
        # Surface this misconfig at startup so it shows in boot logs instead
        # of leaving an operator to debug mysterious 401s.
        logger.warning(
            "test_reset_token_whitespace_padded "
            "raw_token_len=%s stripped_token_len=%s "
            "(handler compares the raw value; clients must send the bytes verbatim)",
            len(raw),
            len(stripped),
        )
    app.include_router(router)
    logger.info("test_reset_route_registered path=%s", _TEST_RESET_PATH)
