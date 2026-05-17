"""Business logic for ``POST /v1/estimate``.

Looks up the caller's ``reading_speeds`` row via the existing
``reading_speed_service.get_for_user`` (Story 3.3 — reused, NOT duplicated),
computes the integer minute count deterministically via
``math.ceil(pages * 60 / pages_per_hour)``, and returns the ``EstimateOut``
DTO with both ``minutes`` and the UX-DR18 ``formatted`` string the SPA
emits verbatim.

The service returns the DTO directly (not the underlying entity) — a
deliberate asymmetry vs. ``reading_speed_service`` because the formatted
string is a presentation concern best colocated with the
``(minutes, formatted)`` pair. The router becomes a pure pass-through;
see Story 4.1 Dev Notes "Why the service returns the DTO instead of the
entity" for the rationale.

Rounding rule: ``math.ceil`` (ceiling) so partial-minute reads round up
to 1, not 0. Python's ``math.ceil`` on a float is stable for the ``(p, n)``
ranges this story serves; see
https://docs.python.org/3/library/math.html#math.ceil.

Identity discipline (NFR6 / architecture §C3 line 388): the service accepts
``sub`` as a parameter, and the only caller (``api/estimate.py``) passes
``principal.subject`` from the JWT — never a body, path, or query value.
The ``EstimateIn`` schema's ``extra="forbid"`` rejects body-level ``sub``
injection attempts at the boundary as 422 ``invalid_input`` before the
service is reached.
"""

from __future__ import annotations

import math

from sqlalchemy.ext.asyncio import AsyncSession

from resource_server.api.schemas.estimate import EstimateOut
from resource_server.services import reading_speed_service
from resource_server.services.duration import format_duration


async def compute_for_user(session: AsyncSession, sub: str, pages: int) -> EstimateOut:
    """Compute the caller's reading-time estimate for ``pages`` pages.

    Args:
        session: SQLAlchemy async session bound to the request lifecycle.
        sub: OIDC subject claim read from the validated JWT by the caller.
        pages: Positive integer page count (``EstimateIn.pages`` already
            enforces ``ge=1`` at the request boundary).

    Returns:
        ``EstimateOut`` with the integer ``minutes`` count and the
        UX-DR18 ``formatted`` string the SPA renders verbatim.

    Raises:
        ReadingSpeedUnsetError: When the caller has no ``reading_speeds``
            row. Propagated from ``reading_speed_service.get_for_user``;
            the existing ``app_exception_handler`` maps this to a 412
            ``reading_speed_unset`` envelope.
    """
    row = await reading_speed_service.get_for_user(session, sub)
    minutes = int(math.ceil(pages * 60 / row.pages_per_hour))
    return EstimateOut(minutes=minutes, formatted=format_duration(minutes))
