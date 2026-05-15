"""GET /health — readiness probe.

Returns 200 only when **all three** of the following are true:
  (a) the BFF database is reachable (a trivial `SELECT 1` succeeds),
  (b) Alembic reports the database is at the head revision (no pending
      migrations; with zero migrations both head and current are None, which
      trivially satisfies the check until Story 1.4 lands the first migration),
  (c) the OIDC discovery doc at ${OIDC_ISSUER_URL}/.well-known/openid-configuration
      is reachable over HTTP (any 2xx response is sufficient; body is not parsed).

On any failure, returns 503 with the archetype error envelope and ErrorCode
`service_unavailable`. The endpoint is always unauthenticated (architecture
§"Operational Details" — healthchecks are always-on).
"""

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

from bff.core.config import AppSettings, settings
from bff.core.database import get_engine
from bff.core.errors import ErrorCode

router = APIRouter(tags=["Infrastructure"])

_BFF_ROOT = Path(__file__).resolve().parents[3]
_ALEMBIC_INI = _BFF_ROOT / "alembic.ini"


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


async def _check_oidc_discovery(
    cfg: AppSettings,
    *,
    client_factory: Callable[..., httpx.AsyncClient] | None = None,
) -> tuple[bool, str]:
    """GET ${OIDC_ISSUER_URL}/.well-known/openid-configuration; require 2xx.

    Honors architecture §C6 timeouts (5s connect, 10s read) and performs zero
    retries — health probes must not paper over startup failures.
    """
    issuer = cfg.oidc_issuer_url.strip()
    if not issuer:
        return False, "OIDC_ISSUER_URL is not configured"
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    timeout = httpx.Timeout(
        connect=cfg.oidc_discovery_connect_timeout,
        read=cfg.oidc_discovery_read_timeout,
        write=cfg.oidc_discovery_read_timeout,
        pool=cfg.oidc_discovery_read_timeout,
    )
    factory = client_factory or httpx.AsyncClient
    try:
        async with factory(timeout=timeout) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return False, f"oidc discovery unreachable: {exc!s}"
    if not (200 <= response.status_code < 300):
        return False, f"oidc discovery returned HTTP {response.status_code}"
    return True, ""


@router.get("/health")
async def health() -> JSONResponse:
    engine = get_engine(settings)

    db_ok, db_detail = await _check_database(engine)
    alembic_ok, alembic_detail = await _check_alembic_at_head(engine)
    oidc_ok, oidc_detail = await _check_oidc_discovery(settings)

    if db_ok and alembic_ok and oidc_ok:
        return JSONResponse(status_code=200, content={"status": "ok"})

    detail = {
        "database": "ok" if db_ok else db_detail,
        "alembic": "ok" if alembic_ok else alembic_detail,
        "oidc_discovery": "ok" if oidc_ok else oidc_detail,
    }
    return JSONResponse(
        status_code=ErrorCode.SERVICE_UNAVAILABLE.http_status,
        content=_build_error_body(ErrorCode.SERVICE_UNAVAILABLE, detail),
    )
