"""GET /health — Resource Server readiness probe.

Returns 200 only when **all three** of the following are true:
  (a) the RS database is reachable (a trivial `SELECT 1` succeeds),
  (b) Alembic reports the database is at the head revision (no pending
      migrations; with zero migrations both head and current are None,
      which trivially satisfies the check until Story 3.3 lands the first
      ReadingSpeed migration),
  (c) the JWKS endpoint at ${OIDC_JWKS_URL} is fetchable over HTTP and
      returns a JWKS-shaped JSON body — a 2xx response with a top-level
      `keys` array (any length >= 0 is acceptable; this is a *liveness*
      probe, not a key-rotation probe).

On any failure, returns 503 with the archetype error envelope and
ErrorCode `service_unavailable`. The endpoint is always unauthenticated
(architecture §"Operational Details" — healthchecks are always-on); the
response body discloses **only** sanitized status labels ("down"/"ok").
Verbose probe details are logged server-side at WARNING, not echoed to the
unauthenticated caller (mirrors the BFF's Story 1.3 review patch P4).

**Why JWKS and not OIDC discovery?** The BFF probes /.well-known/openid-
configuration because it is an OAuth *client* (it visits /authorize,
/token, /end_session). The RS is an OAuth *resource server* — its only
read against Keycloak is the JWKS document used for JWT signature
verification (Story 3.2). Probing JWKS directly is narrower (smaller
surface area) and more honest (asserts the actual dependency, not a proxy
for it). Architecture line 1327 makes this explicit.
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path

import httpx
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from resource_server.core.config import AppSettings, settings
from resource_server.core.database import get_engine
from resource_server.core.errors import ErrorCode

router = APIRouter(tags=["Infrastructure"])
logger = logging.getLogger(__name__)

# Located via env var so the path works in the built image (Dockerfile copies
# alembic.ini to /app/alembic.ini, WORKDIR /app), in local dev / pytest
# (CWD is services/resource-server/), and is overridable in tests. Mirrors
# the BFF's Story 1.3 Review Findings P2 fix.
_ALEMBIC_INI = Path(os.environ.get("ALEMBIC_INI", "alembic.ini"))


def _build_error_body(
    code: ErrorCode, detail: object | None = None
) -> dict[str, object]:
    return {"errorCode": code.code, "message": code.message, "detail": detail}


async def _check_database(engine: AsyncEngine) -> tuple[bool, str]:
    """Run SELECT 1 against the engine; return (ok, detail_on_failure_or_empty)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 -- health probe must catch broadly
        return False, f"database unreachable: {exc!s}"
    return True, ""


def _read_current_revision_sync(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


async def _check_alembic_at_head(engine: AsyncEngine) -> tuple[bool, str]:
    """Compare the database's current Alembic revision against the script head.

    Reads the script head once (synchronous file I/O) then uses an async DB
    connection + `run_sync` to ask MigrationContext for the current revision
    — this is the only async-safe way to talk to MigrationContext over
    aiosqlite (which requires greenlet bridging). With zero migrations
    defined, head is None and current is None ⇒ at-head is True (acceptable
    through Story 3.1; Story 3.3 lands the first migration and this check
    becomes load-bearing).
    """
    try:
        script = ScriptDirectory.from_config(AlembicConfig(str(_ALEMBIC_INI)))
        head_rev = script.get_current_head()
        async with engine.connect() as conn:
            current_rev = await conn.run_sync(_read_current_revision_sync)
    except Exception as exc:  # noqa: BLE001 -- health probe must catch broadly
        return False, f"alembic check failed: {exc!s}"
    if current_rev != head_rev:
        return (
            False,
            f"alembic not at head: current={current_rev!r} head={head_rev!r}",
        )
    return True, ""


async def _check_jwks(
    cfg: AppSettings,
    *,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> tuple[bool, str]:
    """GET ${OIDC_JWKS_URL}; require a 2xx JSON object response carrying a
    top-level `keys` array (any length is acceptable, including zero).

    Liveness, not configuration-correctness. The probe answers a narrow
    question — is Keycloak alive and serving *some* JWKS document on this
    URL? — not whether the keys are actually usable for signature
    verification (that is Story 3.2's territory via PyJWKClient). An empty
    `keys: []` array still passes the probe because a freshly-rotated
    realm momentarily exposes an empty key set; treating that as a /health
    failure would create a startup race against Keycloak's key-cache warm-up.

    Honors architecture §C6 / AR19 timeouts (5s connect, 10s read) and zero
    retries. Follows 3xx redirects (mirrors BFF Story 1.3 Review Findings
    P6 — Keycloak behind ingress with trailing-slash normalization
    302-redirects on this path).
    """
    jwks_url = cfg.oidc_jwks_url.strip()
    if not jwks_url:
        return False, "OIDC_JWKS_URL is not configured"
    timeout = httpx.Timeout(
        connect=cfg.oidc_jwks_connect_timeout,
        read=cfg.oidc_jwks_read_timeout,
        write=cfg.oidc_jwks_read_timeout,
        pool=cfg.oidc_jwks_read_timeout,
    )
    factory = client_factory or httpx.AsyncClient
    try:
        async with factory(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(jwks_url)
    except httpx.HTTPError as exc:
        return False, f"jwks unreachable: {exc!s}"
    if not (200 <= response.status_code < 300):
        return False, f"jwks returned HTTP {response.status_code}"
    try:
        payload = response.json()
    except ValueError as exc:
        return False, f"jwks returned non-JSON body: {exc!s}"
    if not isinstance(payload, dict):
        return False, (f"jwks body is not a JSON object: got {type(payload).__name__}")
    keys = payload.get("keys")
    if not isinstance(keys, list):
        return False, (
            "jwks body is missing a 'keys' array: "
            f"got {type(keys).__name__ if keys is not None else 'None'}"
        )
    return True, ""


@router.get("/health")
async def health() -> JSONResponse:
    engine = get_engine()

    db_ok, db_detail = await _check_database(engine)
    alembic_ok, alembic_detail = await _check_alembic_at_head(engine)
    jwks_ok, jwks_detail = await _check_jwks(settings)

    if db_ok and alembic_ok and jwks_ok:
        return JSONResponse(status_code=200, content={"status": "ok"})

    # Sanitized response body — `_check_*` helpers return rich detail
    # strings (paths, exception messages, hostnames) that are useful for
    # operators but must not leak to an unauthenticated caller. Log the
    # verbose detail server-side and respond with status labels only.
    logger.warning(
        "health probe failed: db=%s alembic=%s jwks=%s",
        db_detail or "ok",
        alembic_detail or "ok",
        jwks_detail or "ok",
    )
    detail = {
        "database": "ok" if db_ok else "down",
        "alembic": "ok" if alembic_ok else "down",
        "jwks": "ok" if jwks_ok else "down",
    }
    return JSONResponse(
        status_code=ErrorCode.SERVICE_UNAVAILABLE.http_status,
        content=_build_error_body(ErrorCode.SERVICE_UNAVAILABLE, detail),
    )
