from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    ADMIN = "admin"
    WRITER = "writer"
    READER = "reader"


@dataclass(frozen=True, kw_only=True)
class Principal:
    subject: str
    user_id: str
    name: str | None = None
    scope: str | None = None
    app_id: str | None = None
    roles: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    claims: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class AuthFunctions:
    """Configured auth callables returned by the auth factory."""

    authenticate_bearer_token: Callable[[str], Awaitable[Principal]]
    get_client_credentials_access_token: Callable[[str], Awaitable[str]]
    get_on_behalf_of_access_token: Callable[[str, str], Awaitable[str]]
    role_mapper: Callable[[str], str]
