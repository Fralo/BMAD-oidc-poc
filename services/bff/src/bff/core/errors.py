import enum
from typing import Any, cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(enum.Enum):
    INTERNAL_ERROR = ("INTERNAL_ERROR", "An unexpected error occurred", 500)
    # legacy: validation_exception_handler now emits INVALID_INPUT (Story 2.2).
    # The member stays for enum-surface stability; no handler emits it on the
    # wire after Story 2.2.
    VALIDATION_ERROR = ("VALIDATION_ERROR", "Request validation failed", 422)
    BAD_REQUEST = ("BAD_REQUEST", "Bad request", 400)
    NOT_FOUND = ("NOT_FOUND", "Resource not found", 404)
    UNAUTHORIZED = ("UNAUTHORIZED", "Authentication required", 401)
    FORBIDDEN = ("FORBIDDEN", "Access forbidden", 403)
    # BMAD_books project-specific codes (architecture §C5). Wire values are
    # lower_snake_case per the documented contract; only codes consumed by
    # this story's surface are added now — later stories add their own as
    # they introduce the consuming handlers.
    SESSION_EXPIRED = ("session_expired", "Session expired or not present", 401)
    SERVICE_UNAVAILABLE = (
        "service_unavailable",
        "A required dependency is unavailable",
        503,
    )
    AUTH_STATE_INVALID = ("auth_state_invalid", "Authorization state invalid", 400)
    CSRF_INVALID = ("csrf_invalid", "CSRF token missing or invalid", 403)
    BOOK_NOT_FOUND = ("book_not_found", "Book not found", 404)
    INVALID_INPUT = ("invalid_input", "Invalid input", 422)

    def __init__(self, code: str, message: str, http_status: int) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status


class AppException(Exception):  # noqa: N818
    def __init__(self, error_code: ErrorCode, detail: str | None = None) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(error_code.message)


def build_error_body(
    error_code: str, message: str, detail: Any = None
) -> dict[str, Any]:
    return {"errorCode": error_code, "message": message, "detail": detail}


async def app_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    app_exc = cast(AppException, exc)
    return JSONResponse(
        status_code=app_exc.error_code.http_status,
        content=build_error_body(
            app_exc.error_code.code, app_exc.error_code.message, app_exc.detail
        ),
    )


async def validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    val_exc = cast(RequestValidationError, exc)
    # Drop the user-supplied `input` value AND the `ctx` slot from each error
    # before serializing. The `input` strip is the Story 1.3 P3 PII-leak fix.
    # The `ctx` strip is the Story 2.2 fix for custom field_validator errors:
    # when a validator raises ValueError, Pydantic stores the raw exception
    # object under `ctx.error`, which is not JSON-serializable. Dropping `ctx`
    # avoids a 500 cascade on the 422 response path.
    sanitized = [
        {k: v for k, v in err.items() if k not in ("input", "ctx")}
        for err in val_exc.errors()
    ]
    return JSONResponse(
        status_code=ErrorCode.INVALID_INPUT.http_status,
        content=build_error_body(
            ErrorCode.INVALID_INPUT.code,
            ErrorCode.INVALID_INPUT.message,
            sanitized,
        ),
    )
