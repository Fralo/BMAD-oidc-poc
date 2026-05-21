"""GET /health — readiness probe.

Returns 200 only when **all three** of the following are true:
  (a) the BFF database is reachable (a trivial `SELECT 1` succeeds),
  (b) Alembic reports the database is at the head revision (no pending
      migrations; with zero migrations both head and current are None, which
      trivially satisfies the check until Story 1.4 lands the first migration),
  (c) the cached OIDC discovery doc is present on `app.state` — Story 7.2's
      lifespan startup hook fetched it once at boot and fail-fast'd on any
      error. /health no longer re-fetches per probe (closes the
      security-review §14 D25 amplification finding).

On any failure, returns 503 with the archetype error envelope and ErrorCode
`service_unavailable`. The endpoint is always unauthenticated (architecture
§"Operational Details" — healthchecks are always-on); the response body
discloses **only** sanitized status labels ("down"). Verbose probe details
are logged server-side, not echoed to the unauthenticated caller.
"""

import logging
import os
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from bff.core.database import get_engine
from bff.core.errors import ErrorCode

router = APIRouter(tags=["Infrastructure"])
logger = logging.getLogger(__name__)

# Located via env var so the path works in the built image (Dockerfile copies
# alembic.ini to /app/alembic.ini, WORKDIR /app) AND in local dev / pytest
# (CWD is services/bff/). Story 1.3 Review Findings P2 — `parents[3]` was
# brittle once `uv sync --no-editable` installed the package under
# site-packages.
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
    through Story 1.3; Story 1.4 lands the first migration and this check
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


def _check_oidc_discovery(request: Request) -> tuple[bool, str]:
    """Presence check on `app.state.oidc_discovery`.

    Story 7.2: the lifespan startup hook fetched the discovery doc once
    and fail-fast'd on any error — so by the time /health runs, the doc
    is either present (return ok) or the process is already dead (return
    down with a hint operators recognize).
    """
    discovery = getattr(request.app.state, "oidc_discovery", None)
    if discovery is None:
        return False, "oidc_discovery not populated on app.state"
    return True, ""


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    engine = get_engine()

    db_ok, db_detail = await _check_database(engine)
    alembic_ok, alembic_detail = await _check_alembic_at_head(engine)
    oidc_ok, oidc_detail = _check_oidc_discovery(request)

    if db_ok and alembic_ok and oidc_ok:
        return JSONResponse(status_code=200, content={"status": "ok"})

    # Sanitized response body — `_check_*` helpers return rich detail
    # strings (paths, exception messages, hostnames) that are useful for
    # operators but must not leak to an unauthenticated caller. Log the
    # verbose detail server-side and respond with status labels only.
    logger.warning(
        "health probe failed: db=%s alembic=%s oidc=%s",
        db_detail or "ok",
        alembic_detail or "ok",
        oidc_detail or "ok",
    )
    detail = {
        "database": "ok" if db_ok else "down",
        "alembic": "ok" if alembic_ok else "down",
        "oidc_discovery": "ok" if oidc_ok else "down",
    }
    return JSONResponse(
        status_code=ErrorCode.SERVICE_UNAVAILABLE.http_status,
        content=_build_error_body(ErrorCode.SERVICE_UNAVAILABLE, detail),
    )
