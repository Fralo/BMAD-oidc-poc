import pytest

from resource_server.auth.contracts import AuthFeatureNotSupportedError
from resource_server.auth.factory import get_auth
from resource_server.auth.models import AuthFunctions
from resource_server.core.config import AppSettings


@pytest.mark.asyncio
async def test_none_auth_bypasses_bearer_validation() -> None:
    auth_fns = get_auth(AppSettings(auth_type="none"))
    principal = await auth_fns.authenticate_bearer_token("any-token-or-none")
    assert principal.user_id == "auth-disabled"
    assert "admin" in principal.roles


@pytest.mark.asyncio
async def test_none_auth_client_credentials_not_supported() -> None:
    auth_fns = get_auth(AppSettings(auth_type="none"))
    with pytest.raises(AuthFeatureNotSupportedError):
        await auth_fns.get_client_credentials_access_token("scope")


def test_get_auth_returns_auth_functions() -> None:
    auth_fns = get_auth(AppSettings(auth_type="none"))
    assert isinstance(auth_fns, AuthFunctions)
