from resource_server.auth.contracts import AuthFeatureNotSupportedError
from resource_server.auth.models import Principal


async def authenticate_bearer_token(token: str) -> Principal:
    _ = token
    return Principal(
        subject="auth-disabled",
        user_id="auth-disabled",
        name="Auth Disabled",
        scope="*",
        app_id="none",
        roles=["admin", "writer", "reader"],
        groups=[],
        claims={"auth_type": "none"},
    )


async def get_client_credentials_access_token(scope: str) -> str:
    _ = scope
    raise AuthFeatureNotSupportedError(
        "Token management is unavailable with AUTH_TYPE=none"
    )


async def get_on_behalf_of_access_token(scope: str, user_token: str) -> str:
    _ = (scope, user_token)
    raise AuthFeatureNotSupportedError("OBO flow is unavailable with AUTH_TYPE=none")
