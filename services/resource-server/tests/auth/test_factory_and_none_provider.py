import builtins
import sys

import pytest

from resource_server.auth.contracts import AuthFeatureNotSupportedError
from resource_server.auth.factory import get_auth
from resource_server.auth.models import AuthFunctions
from resource_server.core.config import AppSettings


def _entra_settings() -> AppSettings:
    return AppSettings(
        auth_type="entra",
        auth_external_issuer="https://issuer.example.test",
        auth_external_jwks_uri="https://issuer.example.test/keys",
        auth_external_token_uri="https://issuer.example.test/token",
        auth_external_client_id="client-id",
        auth_external_client_secret="client-secret",
    )


def test_get_auth_entra_returns_auth_functions() -> None:
    auth_fns = get_auth(_entra_settings())
    assert isinstance(auth_fns, AuthFunctions)


def test_get_auth_errors_when_httpx_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(
        sys.modules,
        "resource_server.auth.entra",
        raising=False,
    )
    original_import = builtins.__import__

    def guarded_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "resource_server.auth.entra":
            raise ModuleNotFoundError("No module named 'httpx'", name="httpx")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    with pytest.raises(RuntimeError, match="AUTH_TYPE=entra requires httpx"):
        get_auth(_entra_settings())


@pytest.mark.asyncio
async def test_none_auth_obo_not_supported() -> None:
    auth_fns = get_auth(AppSettings(auth_type="none"))
    with pytest.raises(AuthFeatureNotSupportedError, match="OBO flow is unavailable"):
        await auth_fns.get_on_behalf_of_access_token("scope", "user-token")
