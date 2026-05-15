# noinspection PyProtectedMember
from httpx import AsyncClient

from bff.core.errors import (
    AppException,
    ErrorCode,
    _build_error_body,
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


def test_app_exception_carries_error_code() -> None:
    exc = AppException(ErrorCode.NOT_FOUND)
    assert exc.error_code is ErrorCode.NOT_FOUND
    assert exc.detail is None
    assert str(exc) == "Resource not found"


def test_app_exception_with_detail() -> None:
    exc = AppException(ErrorCode.NOT_FOUND, detail="id=99")
    assert exc.detail == "id=99"
    assert exc.error_code is ErrorCode.NOT_FOUND


def test_build_error_body_structure() -> None:
    body = _build_error_body("TEST_CODE", "Test message", "extra detail")
    assert body == {
        "errorCode": "TEST_CODE",
        "message": "Test message",
        "detail": "extra detail",
    }


def test_build_error_body_null_detail() -> None:
    body = _build_error_body("CODE", "msg")
    assert body["detail"] is None


async def test_validation_error_via_http(client: AsyncClient) -> None:
    response = await client.post("/test/open")
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
