from typing import Any

import pytest

from resource_server.auth.contracts import AuthFeatureNotSupportedError
from resource_server.auth.entra import make_entra_auth
from resource_server.core.config import AppSettings


def _settings(**overrides: Any) -> AppSettings:
    defaults: dict[str, Any] = {
        "auth_type": "entra",
        "auth_external_issuer": "https://issuer.example.test",
        "auth_external_jwks_uri": "https://issuer.example.test/keys",
        "auth_external_token_uri": "https://example.test/token",
        "auth_external_client_id": "client-id",
        "auth_external_client_secret": "client-secret",
    }
    defaults.update(overrides)
    return AppSettings.model_validate(defaults)


def _settings_without_m2m(**overrides: Any) -> AppSettings:
    defaults: dict[str, Any] = {
        "auth_type": "entra",
        "auth_external_issuer": "https://issuer.example.test",
        "auth_external_jwks_uri": "https://issuer.example.test/keys",
    }
    defaults.update(overrides)
    return AppSettings.model_validate(defaults)


@pytest.mark.asyncio
async def test_client_credentials_raises_when_no_client_secret() -> None:
    auth_fns = make_entra_auth(
        _settings_without_m2m(
            auth_external_token_uri="https://example.test/token",
            auth_external_client_id="client-id",
        )
    )
    with pytest.raises(AuthFeatureNotSupportedError, match="client_secret"):
        await auth_fns.get_client_credentials_access_token("scope://api/.default")


@pytest.mark.asyncio
async def test_client_credentials_raises_when_no_client_id() -> None:
    auth_fns = make_entra_auth(
        _settings_without_m2m(
            auth_external_token_uri="https://example.test/token",
            auth_external_client_secret="client-secret",
        )
    )
    with pytest.raises(AuthFeatureNotSupportedError, match="client_id"):
        await auth_fns.get_client_credentials_access_token("scope://api/.default")


@pytest.mark.asyncio
async def test_obo_raises_when_no_client_secret() -> None:
    auth_fns = make_entra_auth(
        _settings_without_m2m(
            auth_external_token_uri="https://example.test/token",
            auth_external_client_id="client-id",
        )
    )
    with pytest.raises(AuthFeatureNotSupportedError, match="client_secret"):
        await auth_fns.get_on_behalf_of_access_token("scope://api/.default", "token")


@pytest.mark.asyncio
async def test_obo_raises_when_no_client_id() -> None:
    auth_fns = make_entra_auth(
        _settings_without_m2m(
            auth_external_token_uri="https://example.test/token",
            auth_external_client_secret="client-secret",
        )
    )
    with pytest.raises(AuthFeatureNotSupportedError, match="client_id"):
        await auth_fns.get_on_behalf_of_access_token("scope://api/.default", "token")
