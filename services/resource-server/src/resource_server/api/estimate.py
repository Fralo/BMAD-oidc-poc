"""FastAPI router for ``POST /v1/estimate`` (scope-gated).

Per architecture §C3 line 386 (and §C1 line 361 — ``/v1/estimate`` is a
versioned domain API): POST requires the ``reading-speed:read`` OAuth
scope and returns ``{"minutes": <int>, "formatted": <UX-DR18 string>}``
or the appropriate named-error envelope on the negative paths
(412 ``reading_speed_unset``, 403 ``forbidden_scope``, 422 ``invalid_input``,
401 ``session_expired``).

Identity is read from the JWT ``sub`` claim only (architecture §C3 line 388
— "All RS endpoints read user identity from the JWT ``sub`` claim — no
path or body identifier accepted for user"); ``EstimateIn`` carries
``extra="forbid"`` so a body containing ``sub`` is rejected as 422 at the
boundary rather than silently dropped.

The handler is a thin pass-through to ``estimate_service.compute_for_user``,
which returns the ``EstimateOut`` DTO directly (deliberate asymmetry vs.
``reading_speed_service`` — see ``services/estimate_service.py``'s module
docstring).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.api.schemas.estimate import EstimateIn, EstimateOut
from resource_server.auth.models import Principal
from resource_server.auth.oidc_bearer import require_scope
from resource_server.core.database import get_session
from resource_server.services import estimate_service

router = APIRouter(tags=["estimate"])


@router.post("/estimate", response_model=EstimateOut)
async def post_estimate(
    payload: EstimateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
) -> EstimateOut:
    return await estimate_service.compute_for_user(
        session, principal.subject, payload.pages
    )
