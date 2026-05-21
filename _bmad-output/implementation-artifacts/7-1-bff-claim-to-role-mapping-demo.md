# Story 7.1: BFF claim-to-role mapping demo (separation of authN/authZ)

Status: backlog

## Story

As a reviewer reading this POC as a reference implementation,
I want the BFF to map an OIDC claim (`groups` or `memberOf`) to an in-app role and gate at least one endpoint by that role,
so that the POC demonstrates the ACME-TS principle "the IdP authenticates; the BFF owns role mapping and permissions" — even with the project's single-user model.

## Acceptance Criteria

**AC1 — Realm carries a `groups` claim mapper.** `keycloak/realm-bmad-books.json` adds a protocol mapper of type `oidc-group-membership-mapper` that injects the user's group memberships into the id_token's `groups` claim. The `testuser` is pre-seeded into a Keycloak group named `reader`. The `freshuser` is pre-seeded into a group named `reader` AND `admin` (so the two roles can be visibly different in a demo).

**AC2 — BFF defines a `Role` enum and a claim→role mapper.** New module `services/bff/src/bff/auth/role_mapping.py` declares:
```python
class Role(StrEnum):
    READER = "reader"
    ADMIN  = "admin"

def map_claims_to_roles(claims: Mapping[str, Any]) -> frozenset[Role]:
    """Return the set of in-app roles for the given id_token claims.
    Reads the `groups` claim (list[str]); ignores unknown group names."""
```

The mapper is pure (no DB / network) and exhaustively tested for: empty groups → empty roles; unknown group only → empty roles; `reader` only → `{READER}`; `reader + admin` → `{READER, ADMIN}`; missing `groups` claim → empty roles.

**AC3 — Session row carries the mapped roles.** `services/bff/src/bff/models/entities/session.py` gains a `roles: str = Field(default="", nullable=False)` column persisting a comma-separated role list. `session_service.create_session(...)` accepts the mapped role set and persists `",".join(sorted(role.value for role in roles))`. An Alembic migration `0002_session_roles.py` adds the column with default `""` to existing rows.

**AC4 — One demo endpoint is role-gated.** New endpoint `GET /api/me/roles` returns `{"roles": ["reader", "admin"]}` for the current session; new endpoint `GET /api/admin/ping` returns 200 `{"ok": true}` only if the session's roles include `Role.ADMIN`, otherwise 403 `{"errorCode": "forbidden_scope", "message": "..."}` (reuses existing `FORBIDDEN_SCOPE` code; no new ErrorCode needed).

**AC5 — Tests.** Unit tests for `role_mapping.py` (≥90% coverage). Integration tests for `/api/admin/ping` covering: testuser (no admin) → 403; freshuser (has admin) → 200; no session → 401.

## Dependencies

- Closes principle gap **P4** (separation of authN/authZ) from sprint-change-proposal-2026-05-21.md.
- Touches: Keycloak realm, BFF auth module, BFF session model + migration, BFF API surface, tests.
- Does NOT touch the Resource Server (the RS keeps scope-based enforcement; the BFF gains role-based enforcement as a parallel mechanism).

## Notes

- This is a demo story. The POC's single-role product design (PRD §5) doesn't *require* roles. Story value is **architectural illustration** of the ACME pattern, not a product feature.
- No SPA changes required for AC1–AC4; the demo can be exercised with `curl` from the host. A small follow-up could add a `🛡️ Admin: yes/no` line to TopChrome — recorded as **deferred** in Story 7.1's completion notes if the demo lands without UI.
