"""FastAPI router for /v1/reading-speed (GET + PUT, scope-gated).

Per architecture §C3 lines 382–388: GET requires the ``reading-speed:read``
OAuth scope and returns ``{"pages_per_hour": <n>}`` or 412
``reading_speed_unset``; PUT requires ``reading-speed:write`` and upserts the
caller's row (matched on JWT ``sub`` only — never on body/path/query, per
architectural boundary at line 388).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.api.schemas.reading_speed import (
    ReadingSpeedOut,
    ReadingSpeedUpsert,
)
from resource_server.auth.models import Principal
from resource_server.auth.oidc_bearer import require_scope
from resource_server.core.database import get_session
from resource_server.services import reading_speed_service

router = APIRouter(tags=["reading-speed"])


@router.get("/reading-speed", response_model=ReadingSpeedOut)
async def get_reading_speed(
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
) -> ReadingSpeedOut:
    row = await reading_speed_service.get_for_user(session, principal.subject)
    return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)


@router.put("/reading-speed", response_model=ReadingSpeedOut)
async def put_reading_speed(
    payload: ReadingSpeedUpsert,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_scope("reading-speed:write"))],
) -> ReadingSpeedOut:
    row = await reading_speed_service.upsert(
        session, principal.subject, payload.pages_per_hour
    )
    return ReadingSpeedOut(pages_per_hour=row.pages_per_hour)
