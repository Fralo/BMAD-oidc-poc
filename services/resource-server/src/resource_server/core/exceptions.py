"""Domain exceptions for the Resource Server.

Business code raises subclasses of ``AppException`` (defined in
``core/errors.py``) rather than ``HTTPException`` so the single
archetype-emitted ``app_exception_handler`` can map every domain failure to
the standard ``{errorCode, message, detail}`` envelope.

See architecture §"Communication Patterns / Error handling (backend
services)" lines 735–749. The architecture's example calls the base
``BFFError``; the RS's archetype emits ``AppException`` — same shape,
different name.
"""

from __future__ import annotations

from resource_server.core.errors import AppException, ErrorCode


class ReadingSpeedUnsetError(AppException):
    """Raised by ``reading_speed_service.get_for_user`` when the caller's
    ``sub`` has no ``reading_speeds`` row. Maps to HTTP 412 with
    ``errorCode: "reading_speed_unset"`` via the existing
    ``app_exception_handler``.
    """

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(ErrorCode.READING_SPEED_UNSET, detail)
