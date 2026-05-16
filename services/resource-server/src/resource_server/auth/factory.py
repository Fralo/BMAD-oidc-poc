from collections.abc import Callable

from resource_server.auth import none as none_auth
from resource_server.auth.models import AuthFunctions
from resource_server.auth.role_mapping import identity_role_mapper
from resource_server.core.config import AppSettings


def get_auth(settings: AppSettings) -> AuthFunctions:
    """Return configured auth functions for the given auth_type via dict-dispatch."""

    def _build_none() -> AuthFunctions:
        return AuthFunctions(
            authenticate_bearer_token=none_auth.authenticate_bearer_token,
            get_client_credentials_access_token=none_auth.get_client_credentials_access_token,
            get_on_behalf_of_access_token=none_auth.get_on_behalf_of_access_token,
            role_mapper=identity_role_mapper,
        )

    def _build_entra() -> AuthFunctions:
        try:
            from resource_server.auth.entra import make_entra_auth  # noqa: PLC0415
        except ModuleNotFoundError as exc:
            if exc.name == "httpx":
                msg = (
                    "AUTH_TYPE=entra requires httpx at runtime. "
                    "Install runtime dependencies before starting the app."
                )
                raise RuntimeError(msg) from exc
            raise
        return make_entra_auth(settings)

    def _build_oidc_bearer() -> AuthFunctions:
        try:
            from resource_server.auth.oidc_bearer import (  # noqa: PLC0415
                make_oidc_bearer_auth,
            )
        except ModuleNotFoundError as exc:
            if exc.name == "jwt":
                msg = (
                    "AUTH_TYPE=oidc_bearer requires pyjwt[crypto] at runtime. "
                    "Install runtime dependencies before starting the app."
                )
                raise RuntimeError(msg) from exc
            raise
        return make_oidc_bearer_auth(settings)

    builders: dict[str, Callable[[], AuthFunctions]] = {
        "none": _build_none,
        "entra": _build_entra,
        "oidc_bearer": _build_oidc_bearer,
    }
    builder = builders.get(settings.auth_type)
    if builder is None:
        raise ValueError(f"Unknown auth_type: {settings.auth_type!r}")
    return builder()
