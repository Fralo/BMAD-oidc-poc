import logging

import pytest
from httpx import AsyncClient

from resource_server.auth.dependencies import get_auth_functions
from resource_server.main import app

from .conftest import mock_auth_functions_reader_principal

AUTH_DEPS_LOGGER = "resource_server.auth.dependencies"


class TestForbiddenSanitization:
    async def test_forbidden_does_not_reveal_role_name(
        self, entra_client: AsyncClient
    ) -> None:
        app.dependency_overrides[get_auth_functions] = (
            mock_auth_functions_reader_principal
        )
        try:
            response = await entra_client.post(
                "/test/admin-required",
                json={"value": "X"},
                headers={"Authorization": "Bearer valid-token"},
            )
            assert response.status_code == 403
            body = response.json()
            assert body["errorCode"] == "FORBIDDEN"
            assert body["message"] == "Access forbidden"
            assert body["detail"] is None
            assert "admin" not in str(body).lower()
        finally:
            app.dependency_overrides.pop(get_auth_functions, None)

    async def test_role_failure_logged_at_warning(
        self, entra_client: AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        app.dependency_overrides[get_auth_functions] = (
            mock_auth_functions_reader_principal
        )
        try:
            with caplog.at_level(logging.WARNING, logger=AUTH_DEPS_LOGGER):
                await entra_client.post(
                    "/test/admin-required",
                    json={"value": "X"},
                    headers={"Authorization": "Bearer valid-token"},
                )
            warning_records = [
                r
                for r in caplog.records
                if r.levelno == logging.WARNING and r.name == AUTH_DEPS_LOGGER
            ]
            assert len(warning_records) >= 1
            assert "admin" in warning_records[0].message
        finally:
            app.dependency_overrides.pop(get_auth_functions, None)
