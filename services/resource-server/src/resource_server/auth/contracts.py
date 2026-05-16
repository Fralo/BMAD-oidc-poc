class AuthError(Exception):
    """Base error for auth/authz subsystem failures."""


class UnauthorizedError(AuthError):
    """Raised when token authentication fails."""


class ForbiddenError(AuthError):
    """Raised when authn succeeds but authz fails."""


class AuthFeatureNotSupportedError(AuthError):
    """Raised when provider cannot fulfill requested capability."""
