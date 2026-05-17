import enum
from typing import Any, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(enum.Enum):
    INTERNAL_ERROR = ("INTERNAL_ERROR", "An unexpected error occurred", 500)
    VALIDATION_ERROR = ("VALIDATION_ERROR", "Request validation failed", 422)
    BAD_REQUEST = ("BAD_REQUEST", "Bad request", 400)
    NOT_FOUND = ("NOT_FOUND", "Resource not found", 404)
    UNAUTHORIZED = ("UNAUTHORIZED", "Authentication required", 401)
    FORBIDDEN = ("FORBIDDEN", "Access forbidden", 403)
    # BMAD_books project-specific codes (architecture §C5). Wire values are
    # lower_snake_case per the documented contract; only codes consumed by
    # this story's surface are added now — later stories add their own as
    # they introduce the consuming handlers (Story 4.x: RESOURCE_SERVER_UNAVAILABLE
    # on the BFF; BFF-only codes BOOK_NOT_FOUND, AUTH_STATE_INVALID, CSRF_INVALID
    # already landed in Epic 1).
    SERVICE_UNAVAILABLE = (
        "service_unavailable",
        "A required dependency is unavailable",
        503,
    )
    SESSION_EXPIRED = (
        "session_expired",
        "Authentication required",
        401,
    )
    FORBIDDEN_SCOPE = (
        "forbidden_scope",
        "Required scope is missing",
        403,
    )
    READING_SPEED_UNSET = (
        "reading_speed_unset",
        "Reading speed not set for this user",
        412,
    )
    INVALID_INPUT = (
        "invalid_input",
        "Request validation failed",
        422,
    )

    def __init__(self, code: str, message: str, http_status: int) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status


class AppException(Exception):  # noqa: N818
    def __init__(self, error_code: ErrorCode, detail: str | None = None) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(error_code.message)


def _build_error_body(
    error_code: str, message: str, detail: Any = None
) -> dict[str, Any]:
    return {"errorCode": error_code, "message": message, "detail": detail}


async def app_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    app_exc = cast(AppException, exc)
    return JSONResponse(
        status_code=app_exc.error_code.http_status,
        content=_build_error_body(
            app_exc.error_code.code, app_exc.error_code.message, app_exc.detail
        ),
    )


async def validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    val_exc = cast(RequestValidationError, exc)
    # Drop the user-supplied `input` value from each error before serializing.
    # Pydantic includes it verbatim; echoing it back to the client leaks raw
    # request data (passwords, tokens, PII) into 422 responses. The BFF closed
    # this in Story 1.3 review patch P3 — mirror exactly here for cross-service
    # consistency. Project-specific wire value is `invalid_input` per
    # architecture §C5 (replaces the archetype's `VALIDATION_ERROR`).
    sanitized = [
        {k: v for k, v in err.items() if k != "input"} for err in val_exc.errors()
    ]
    return JSONResponse(
        status_code=ErrorCode.INVALID_INPUT.http_status,
        content=_build_error_body(
            ErrorCode.INVALID_INPUT.code,
            ErrorCode.INVALID_INPUT.message,
            sanitized,
        ),
    )
