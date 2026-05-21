import logging
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from resource_server.aop.auth_logging import AuthDecision, emit_auth_decision
from resource_server.auth.contracts import UnauthorizedError
from resource_server.auth.factory import get_auth
from resource_server.auth.models import AuthFunctions, Principal, Role
from resource_server.auth.oidc_discovery import OidcDiscovery, get_oidc_discovery
from resource_server.core.config import settings
from resource_server.core.errors import AppException, ErrorCode

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_functions(
    discovery: Annotated[OidcDiscovery, Depends(get_oidc_discovery)],
) -> AuthFunctions:
    # Story 7.2: built per-request because `get_auth(settings, discovery)`
    # closes over the cached discovery doc; the previous @lru_cache returned
    # a closure that captured a stale empty discovery at first-call time.
    # Construction is just dataclass assembly — negligible overhead.
    return get_auth(settings, discovery)


async def get_bearer_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str | None:
    if credentials is None:
        return None
    return credentials.credentials


async def get_current_principal(
    token: Annotated[str | None, Depends(get_bearer_token)],
    auth_fns: Annotated[AuthFunctions, Depends(get_auth_functions)],
) -> Principal:
    if settings.auth_type == "none":
        return await auth_fns.authenticate_bearer_token(token or "")
    if token is None:
        raise AppException(ErrorCode.UNAUTHORIZED)
    try:
        principal = await auth_fns.authenticate_bearer_token(token)
    except UnauthorizedError as exc:
        logger.warning("Bearer token authentication failed: %s", exc)
        raise AppException(ErrorCode.UNAUTHORIZED) from exc
    except AppException:
        raise
    except Exception as exc:
        logger.warning("Unexpected authentication error: %s", exc)
        emit_auth_decision(
            decision=AuthDecision.DENY,
            reason="auth_unexpected_error",
            sub=None,
        )
        raise AppException(ErrorCode.UNAUTHORIZED) from exc
    return principal


async def require_auth(
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Principal:
    return principal


def require_role(required_role: Role):
    async def _dependency(
        principal: Annotated[Principal, Depends(get_current_principal)],
        auth_fns: Annotated[AuthFunctions, Depends(get_auth_functions)],
    ) -> Principal:
        roles = {role.lower() for role in principal.roles}
        external_role = auth_fns.role_mapper(required_role.value).lower()
        if external_role not in roles:
            logger.warning(
                "Role check failed: principal %s lacks role %s (they have %d roles)",
                principal.subject,
                required_role.value,
                len(roles),
            )
            emit_auth_decision(
                decision=AuthDecision.DENY,
                reason=f"role_denied:{required_role.value}",
                sub=principal.subject,
            )
            raise AppException(ErrorCode.FORBIDDEN)
        return principal

    return _dependency
