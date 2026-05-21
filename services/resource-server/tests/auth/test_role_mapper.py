from resource_server.auth.factory import get_auth
from resource_server.auth.models import AuthFunctions
from resource_server.auth.oidc_discovery import OidcDiscovery
from resource_server.auth.role_mapping import identity_role_mapper
from resource_server.core.config import AppSettings

_DUMMY_DISCOVERY = OidcDiscovery(
    issuer="i",
    authorization_endpoint="a",
    token_endpoint="t",
    jwks_uri="j",
    end_session_endpoint="e",
    revocation_endpoint="r",
)


class TestAuthFunctionsRoleMapper:
    def test_default_role_mapper_is_identity(self) -> None:
        auth_fns = get_auth(AppSettings(auth_type="none"), _DUMMY_DISCOVERY)
        assert auth_fns.role_mapper("admin") == "admin"
        assert auth_fns.role_mapper("reader") == "reader"

    def test_custom_role_mapper_can_be_injected(self) -> None:
        def guid_mapper(role: str) -> str:
            return {"admin": "guid-admin-001"}.get(role, role)

        from unittest.mock import AsyncMock

        auth_fns = AuthFunctions(
            authenticate_bearer_token=AsyncMock(),
            get_client_credentials_access_token=AsyncMock(),
            get_on_behalf_of_access_token=AsyncMock(),
            role_mapper=guid_mapper,
        )
        assert auth_fns.role_mapper("admin") == "guid-admin-001"
        assert auth_fns.role_mapper("reader") == "reader"

    def test_identity_role_mapper_returns_role_unchanged(self) -> None:
        assert identity_role_mapper("admin") == "admin"
        assert identity_role_mapper("custom-role") == "custom-role"
