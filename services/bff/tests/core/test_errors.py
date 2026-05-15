from httpx import AsyncClient

from bff.core.errors import (
    AppException,
    ErrorCode,
    build_error_body,
)


def test_error_code_not_found() -> None:
    assert ErrorCode.NOT_FOUND.code == "NOT_FOUND"
    assert ErrorCode.NOT_FOUND.message == "Resource not found"
    assert ErrorCode.NOT_FOUND.http_status == 404


def test_error_code_validation_error() -> None:
    assert ErrorCode.VALIDATION_ERROR.code == "VALIDATION_ERROR"
    assert ErrorCode.VALIDATION_ERROR.http_status == 422


def test_error_code_internal_error() -> None:
    assert ErrorCode.INTERNAL_ERROR.code == "INTERNAL_ERROR"
    assert ErrorCode.INTERNAL_ERROR.http_status == 500


def test_error_code_unauthorized() -> None:
    assert ErrorCode.UNAUTHORIZED.code == "UNAUTHORIZED"
    assert ErrorCode.UNAUTHORIZED.http_status == 401


def test_error_code_forbidden() -> None:
    assert ErrorCode.FORBIDDEN.code == "FORBIDDEN"
    assert ErrorCode.FORBIDDEN.http_status == 403


def test_error_code_auth_state_invalid() -> None:
    # Story 1.5 — wire value is lower_snake_case per architecture §C5.
    assert ErrorCode.AUTH_STATE_INVALID.code == "auth_state_invalid"
    assert ErrorCode.AUTH_STATE_INVALID.message == "Authorization state invalid"
    assert ErrorCode.AUTH_STATE_INVALID.http_status == 400


def test_csrf_invalid_enum_shape() -> None:
    # Story 1.6 — wire value is lower_snake_case per architecture §C5; 403 per
    # architecture §Format Patterns line 684.
    assert ErrorCode.CSRF_INVALID.code == "csrf_invalid"
    assert ErrorCode.CSRF_INVALID.message == "CSRF token missing or invalid"
    assert ErrorCode.CSRF_INVALID.http_status == 403


def test_app_exception_carries_error_code() -> None:
    exc = AppException(ErrorCode.NOT_FOUND)
    assert exc.error_code is ErrorCode.NOT_FOUND
    assert exc.detail is None
    assert str(exc) == "Resource not found"


def test_app_exception_with_detail() -> None:
    exc = AppException(ErrorCode.NOT_FOUND, detail="id=99")
    assert exc.detail == "id=99"
    assert exc.error_code is ErrorCode.NOT_FOUND


def testbuild_error_body_structure() -> None:
    body = build_error_body("TEST_CODE", "Test message", "extra detail")
    assert body == {
        "errorCode": "TEST_CODE",
        "message": "Test message",
        "detail": "extra detail",
    }


def testbuild_error_body_null_detail() -> None:
    body = build_error_body("CODE", "msg")
    assert body["detail"] is None


async def test_validation_error_via_http(client_with_csrf: AsyncClient) -> None:
    # Story 1.6: CSRF middleware now intercepts POST without the cookie/header
    # before validation runs. Use the pre-seeded fixture so the request reaches
    # the validator and surfaces the 422 envelope under test.
    response = await client_with_csrf.post("/test/open")
    assert response.status_code == 422
    data = response.json()
    assert data["errorCode"] == "VALIDATION_ERROR"
    assert data["message"] == "Request validation failed"
    assert "detail" in data


def test_app_exception_handler_returns_json() -> None:
    import asyncio
    import json
    from unittest.mock import MagicMock

    from bff.core.errors import app_exception_handler

    exc = AppException(ErrorCode.NOT_FOUND, detail="id=42")
    request = MagicMock()
    response = asyncio.run(app_exception_handler(request, exc))
    assert response.status_code == 404
    raw = response.body
    body_str: str = raw.decode() if isinstance(raw, bytes) else str(raw)
    body = json.loads(body_str)
    assert body["errorCode"] == "NOT_FOUND"
    assert body["message"] == "Resource not found"
    assert body["detail"] == "id=42"
