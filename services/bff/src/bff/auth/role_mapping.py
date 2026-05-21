"""Pure claim → in-app role mapper for the BFF (Story 7.1).

The BFF (not the AS) owns the mapping from raw OIDC `groups` claim values
to in-app `Role` enum members. This is the ACME-TS principle P4 boundary:
the IdP authenticates and asserts attributes; the application maps
attributes to roles and enforces them.

This module is pure (no DB, no network, no I/O). Consumers:
- `bff.api.auth` — calls `map_claims_to_roles` at the /auth/callback success path
- `bff.services.session_service` — calls `serialize_roles` to persist the role set
- `bff.api.me` — calls `deserialize_roles` + `Role` to serve `/api/me/roles` and gate `/api/admin/ping`
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    READER = "reader"
    ADMIN = "admin"


def map_claims_to_roles(claims: Mapping[str, Any]) -> frozenset[Role]:
    """Return the set of in-app roles for the given id_token claims.

    Reads the `groups` claim (list[str]); ignores unknown group names;
    returns the empty frozenset if `groups` is missing, not a list, or empty.
    Idempotent: passing the same claims dict returns an equal frozenset.
    """
    raw_groups = claims.get("groups")
    if not isinstance(raw_groups, list):
        return frozenset()
    out: set[Role] = set()
    for group in raw_groups:
        if not isinstance(group, str):
            continue
        try:
            out.add(Role(group))
        except ValueError:
            # Unknown group name → ignore (per Story 7.1 AC2).
            continue
    return frozenset(out)


def serialize_roles(roles: frozenset[Role]) -> str:
    """Serialize a role set to the comma-separated sorted string used in DB storage.

    `frozenset({Role.READER, Role.ADMIN})` → `"admin,reader"` regardless of
    insertion order. The empty frozenset serializes to `""` (matches the
    column's NOT NULL `default=""` contract — see `sessions.roles`).
    """
    return ",".join(sorted(r.value for r in roles))


def deserialize_roles(blob: str) -> list[str]:
    """Parse a stored `sessions.roles` blob into a list of role-name strings.

    Empty string → empty list. Preserves the stored sort order (alphabetical
    by `serialize_roles`'s invariant). Returns raw strings rather than Role
    enum members because the wire surface (`GET /api/me/roles`) emits strings;
    callers needing typed members can re-wrap via `Role(...)`.
    """
    return [r for r in blob.split(",") if r]
