---
status: ready-for-dev
story_key: 7-1-bff-claim-to-role-mapping-demo
epic: 7
created: 2026-05-21
baseline_commit: 760cbb2
supersedes: (none — first story in Epic 7)
prerequisites: |
  Epic 1–6 all done. Epic 7 was introduced 2026-05-21 via Sprint Change
  Proposal at `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md`
  to close three ACME-TS principles-audit gaps (P4 / P6 / P8). This story
  closes **P4 (separation of authN/authZ)** with a BFF claim→role mapper
  and a single role-gated demo endpoint. The PKCE removal carried by the
  same proposal (Groups A–H) is the **assumed baseline** — i.e. this story
  is written against the post-`760cbb2` source tree, where:
    • `services/bff/src/bff/auth/pkce.py` is **deleted**
    • `services/bff/src/bff/auth/keycloak_cookie_session.py` no longer
      references `code_verifier` / `code_challenge`
    • `services/bff/src/bff/services/session_service.py:create_auth_state`
      returns `entities.AuthState` (no tuple)
    • `services/bff/src/bff/models/entities/auth_state.py` keeps
      `code_verifier` as a vestigial nullable column
    • `keycloak/realm-bmad-books.json` has no `pkce.code.challenge.method`
      attribute and the `bmad-books-bff` client description says
      "client_secret_basic; no PKCE".
  If the working tree is **behind** that baseline (e.g. branch
  `worktree-agent-a1f11fc311ebed2e7` carries `d26dd7c` as HEAD), the dev
  agent must first rebase / fast-forward onto the branch that carries the
  PKCE-removal commit (`simplified-implementation` HEAD = `760cbb2`)
  before starting Story 7.1 — otherwise the new realm + BFF surfaces will
  conflict with PKCE artefacts that the proposal already retired.
parallel_with: |
  Stories 7.2 (`oidc-discovery-bootstrap`) and 7.3
  (`structured-auth-decision-logs`) are being created **in sibling
  worktrees in parallel** with this one. None of the three Epic 7 stories
  depend on each other at the spec level (the Sprint Change Proposal's
  recommended dev-sequence — 7.3 → 7.2 → 7.1 — is an *implementation*
  ordering convenience, not a hard dependency). Story 7.1's scope is
  strictly contained inside `services/bff/`, `services/bff/tests/`,
  `services/bff/alembic/versions/`, and `keycloak/realm-bmad-books.json`.
  Story 7.1 does **NOT** touch any RS / SPA / e2e / compose / docs files.
---

# Story 7.1: BFF claim-to-role mapping demo (separation of authN/authZ)

Status: ready-for-dev

<!-- Sprint: Epic 7 (ACME-TS Principles Alignment). First story in Epic 7. -->
<!-- Source of truth: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §4 Group I + §5 (Future work). -->
<!-- Closes principles-audit gap **P4** (separation of authN/authZ via BFF role mapping). -->

## Story

As a reviewer reading this POC as a reference implementation for an upcoming ACME-TS client engagement,
I want the BFF to map an OIDC claim (`groups`) to an in-app `Role` enum and gate at least one endpoint by that role,
so that the POC demonstrates the ACME-TS principle **"the IdP authenticates; the BFF owns role mapping and permissions"** — even with the project's single-user product model.

## Why this story exists (read this first)

The BMAD_books PRD §5 declares a **single-role product**: every authenticated user has the same capabilities (CRUD on their books, GET/PUT their reading speed, POST an estimate). The product **does not need** roles to ship. So why is Story 7.1 in scope?

Because the POC is being used as a **reference implementation** for the user's real-project ACME-TS engagement, where multi-role authZ is mandatory. The ACME-TS auth-design principles list pasted into the 2026-05-21 `bmad-correct-course` session names *separation of authN/authZ* as principle **P4**: the IdP (Keycloak) is responsible only for *authenticating* the user; the application (the BFF) is responsible for mapping the resulting claim set into the *roles* and *permissions* the application uses to gate behavior. The current POC delegates **both** to Keycloak (scope-based enforcement at the RS via `require_scope("reading-speed:read")` etc.) and has no in-app role concept on the BFF — so P4 is an audit gap.

Story 7.1's value is therefore **architectural illustration**, not product functionality:

1. It introduces the `Role` enum on the BFF — the artefact the rest of the application would consult to decide "may this caller do X?".
2. It introduces the `groups`-claim → `Role` mapper — the *single place* the application's authZ depends on the IdP's authN output. The rest of the BFF treats `Role` opaquely.
3. It introduces **one** role-gated demo endpoint (`GET /api/admin/ping`) so the wiring is exercised end-to-end (realm → id_token claim → session row → endpoint decision).
4. It introduces the realm-side `groups` setup that a real ACME-TS deployment would carry.

Scope-based authZ at the Resource Server (Story 3.2 / 3.3) **remains unchanged** and is a separate mechanism — Story 7.1 does NOT replace it. The BFF gains a *parallel* role-based mechanism. A real ACME-TS deployment would use both: the IdP enforces scopes on token issuance and the RS validates them on token presentation (preventing horizontal token misuse); the BFF translates claims into application roles and gates business operations on them.

## Scope (read this carefully)

Story 7.1 lands inside **four directories only**:

1. `keycloak/realm-bmad-books.json` — add the `groups` array, the `oidc-group-membership-mapper`, and the user→group memberships.
2. `services/bff/src/bff/` — new `auth/role_mapping.py`, edits to `models/entities/session.py`, edits to `services/session_service.py`, new `api/admin.py`, new endpoint on `api/me.py` (`/api/me/roles`), and one router registration in `main.py`.
3. `services/bff/alembic/versions/` — new migration `0003_session_roles.py` (note: **0003**, not 0002 — `0002_add_books` already exists; the planning spec's "0002_session_roles" wording is incorrect and is corrected here).
4. `services/bff/tests/` — new `auth/test_role_mapping.py`, new `api/test_admin.py`, edits to `api/test_me.py`, edits to `services/test_session_service.py`, edits to `models/entities/test_session.py` (if it exists; otherwise add to the closest mirror).

What this story **does NOT do** (each line is a hard constraint at code-review time):

- **Does NOT touch the Resource Server.** RS keeps scope-based enforcement on `/v1/reading-speed*` and `/v1/estimate`; no `Role` concept enters `services/resource-server/`.
- **Does NOT touch the SPA.** The demo is exercised with `curl` from the host. A small UI follow-up could surface "🛡️ Admin: yes/no" in TopChrome — explicitly **deferred** (see Completion Notes).
- **Does NOT touch e2e / Playwright.** No new specs. The proof is BFF integration tests + manual curl.
- **Does NOT touch compose.** No service-graph changes. Same five containers.
- **Does NOT touch `docs/`.** No security-review / coverage-report / README edits. (A future ACME-TS reference-impl docs sweep can cite Story 7.1 then.)
- **Does NOT remove or re-encode the BFF's existing `/api/me` shape.** `GET /api/me` continues to return `{sub, preferred_username}` byte-for-byte; the new role surface lives at `GET /api/me/roles` so existing SPA / Playwright callers are unaffected.
- **Does NOT add `offline_access` back into the requested scopes.** The Story 1.5 P3 fix that dropped `offline_access` (`services/bff/src/bff/api/auth.py:67–71`) stands — confidential clients get refresh tokens with the plain `authorization_code` grant.
- **Does NOT add a new `FORBIDDEN_SCOPE` error code to the BFF.** The 403 returned by `/api/admin/ping` reuses the existing BFF `ErrorCode.FORBIDDEN` (`services/bff/src/bff/core/errors.py:18`); see the AC4 note on why the original planning spec's "reuse `FORBIDDEN_SCOPE`" wording was wrong (that code lives only on the RS — `services/resource-server/src/resource_server/core/errors.py:32` — and the BFF must not invent a parallel ErrorCode for a single demo endpoint).
- **Does NOT touch the existing `0002_add_books.py` migration**, the existing `auth_states` table (vestigial `code_verifier` column stays), the `csrf` middleware, the resource-server-client, or any of the books-domain code.

## Acceptance Criteria

> Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §4 Group I (proposal) + the original planning spec at `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md` as committed in `760cbb2`. Re-derived and tightened here with concrete file paths, exact API names, and the corrections noted in **Scope** above.

### AC1 — Realm carries a `groups` claim mapper and pre-seeded group memberships

**Given** the Keycloak realm definition file at `keycloak/realm-bmad-books.json`,
**When** the developer inspects the post-Story-7.1 realm,
**Then** the file contains:

1. A new top-level `"groups"` array with **two** group definitions:
   - `{"name": "reader", "path": "/reader"}`
   - `{"name": "admin",  "path": "/admin"}`
   (Keycloak realm-import format — `path` is the canonical group identifier; nested groups are not used.)

2. The existing `bmad-books-bff` client's `"protocolMappers"` array gains a new entry of type `"oidc-group-membership-mapper"`:
   ```jsonc
   {
     "name": "groups",
     "protocol": "openid-connect",
     "protocolMapper": "oidc-group-membership-mapper",
     "consentRequired": false,
     "config": {
       "claim.name": "groups",
       "full.path": "false",
       "id.token.claim": "true",
       "access.token.claim": "true",
       "userinfo.token.claim": "false",
       "jsonType.label": "String"
     }
   }
   ```
   `"full.path": "false"` makes the claim emit short names (`["reader", "admin"]`) rather than path strings (`["/reader", "/admin"]`) — the BFF mapper at AC2 expects short names.

3. The pre-seeded `testuser` gets `"groups": ["/reader"]` added to its user definition (so testuser has the `reader` role only).

4. The pre-seeded `freshuser` gets `"groups": ["/reader", "/admin"]` added to its user definition (so freshuser has **both** roles — the two-role case the demo needs to be visibly different from testuser).

**And** `docker compose up keycloak --force-recreate` completes realm import without warnings (Keycloak 26 imports the new `groups` array on first startup; the `RealmImportProvider` logs include the two group definitions).

**And** an unauthenticated request to Keycloak's userinfo endpoint after a freshuser login carries `"groups": ["reader", "admin"]` in the id_token claim set (verifiable via a synthetic-IdP test in AC5; see also the Playwright fixture's existing testuser/freshuser logins in `e2e/fixtures/helpers.ts` — those tests are NOT touched here but the realm change is forward-compatible with them).

> **Failure-prevention note (realm-import idempotency):** Keycloak's realm import is idempotent on `id` and `name`, but the `bmad-books-bff` client's `protocolMappers` array is replaced wholesale on import — *don't* split the change across two edits to the same array. The single edit must add the `"groups"` mapper alongside the existing `aud-resource-server` and `sub` mappers so the post-import array has three entries.

> **Failure-prevention note (group path vs. name):** Story 7.1's mapper config uses `"full.path": "false"` for a reason: the BFF's pure-mapper (AC2) uses simple string membership tests (`"reader" in claims["groups"]`). If `full.path` were `true`, the claim would carry `["/reader", "/admin"]` and the BFF mapper would silently fail (no `"reader"` match) — the unit tests at AC5 would catch that, but the realm config is the load-bearing source of truth so spell it out here.

### AC2 — `Role` enum + pure claim→role mapper

**Given** the BFF auth package at `services/bff/src/bff/auth/`,
**When** the developer inspects the post-Story-7.1 source tree,
**Then** the file `services/bff/src/bff/auth/role_mapping.py` exists with **exactly** the following public API:

```python
"""Claim → in-app Role mapping (Story 7.1 — ACME-TS principle P4).

Separation of authN/authZ: Keycloak authenticates and emits a `groups`
claim in the id_token. The BFF owns the mapping from the claim's
string values to the application's `Role` enum. The rest of the BFF
never reaches into `claims["groups"]` directly — it consults `Role`.

This module is **pure**: no DB, no network, no logging. It is exhaustively
tested at the unit level and is the single source of truth for what
counts as "admin" in this codebase.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final


class Role(StrEnum):
    """In-app role labels. Wire values match the Keycloak group names
    declared in `keycloak/realm-bmad-books.json` (see Story 7.1 AC1)."""

    READER = "reader"
    ADMIN = "admin"


# Single source of truth for the claim name. If a future Keycloak realm
# emits memberships under a different name (e.g. `memberOf`), change the
# realm config OR change this constant — not both.
_GROUPS_CLAIM_NAME: Final[str] = "groups"


def map_claims_to_roles(claims: Mapping[str, Any]) -> frozenset[Role]:
    """Return the set of in-app roles for the given id_token claims.

    Reads the `groups` claim (expected `list[str]` of short group names —
    see realm config `full.path: "false"`). Unknown group names are
    silently ignored. Missing / non-list / non-string-element values
    yield an empty set.

    The return type is `frozenset[Role]` (not `set[Role]`) so callers
    can use the result as a dict key, hash it, or compare equality
    without worrying about mutation. The function never raises.
    """
    raw = claims.get(_GROUPS_CLAIM_NAME)
    if not isinstance(raw, list):
        return frozenset()
    roles: set[Role] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        try:
            roles.add(Role(item))
        except ValueError:
            # Unknown group name — silently drop. Logging this would
            # noise up the auth-decision log surface (Story 7.3's
            # concern) without helping diagnose anything.
            continue
    return frozenset(roles)
```

**And** the module has **zero** imports from `bff.core.*`, `bff.api.*`, `bff.services.*`, `bff.models.*`, `bff.observability.*`, `sqlmodel`, `sqlalchemy`, `httpx`, `jwt`, or `bff.auth.csrf` / `bff.auth.keycloak_cookie_session` (verified by the unit-test file via a static import check — see AC5). The mapper is pure and depends only on the Python stdlib + `bff.auth.role_mapping` itself.

> **Failure-prevention note (StrEnum vs Enum):** Python 3.14 `StrEnum` (PEP 663) gives us a string-valued enum where `Role.READER == "reader"` is `True` and `str(Role.READER) == "reader"`. This is what we want for both wire serialization (the new `/api/me/roles` response — AC4) and DB storage (the comma-joined `Session.roles` column — AC3). Do NOT use plain `Enum` and override `__str__`; do NOT use `IntEnum`.

> **Failure-prevention note (don't fold the mapper into `session_service.py`):** The mapper is a separate module because (a) it has no DB / async dependencies and unit-testing it inline in `session_service.py`'s file would force test-collection of a much larger surface, and (b) ACME-TS principle P4 is precisely "this code is the seam — keep it visible." Inlining defeats the architectural illustration.

### AC3 — `Session.roles` column + Alembic migration + `SessionService.create_session` accepts roles

**Given** the BFF session model at `services/bff/src/bff/models/entities/session.py`,
**When** the developer inspects the post-Story-7.1 model,
**Then** the `Session` SQLModel gains exactly one new column:

```python
# Story 7.1 — ACME-TS principle P4. Comma-separated, sorted, role
# wire-values (e.g. "admin,reader"). Empty string = no roles (the
# `groups` claim was missing, empty, or carried only unknown names).
# Stored as a denormalized string for simplicity — the POC has at most
# 2 roles per session and never queries by-role on the DB layer.
roles: str = Field(default="", nullable=False)
```

The column is declared with `default=""` and `nullable=False` so existing rows (the column is added in the Alembic migration with a server default of `""`) and brand-new rows (no `roles=` kwarg passed) both end up at the empty-string sentinel.

**And** a new Alembic migration `services/bff/alembic/versions/0003_session_roles.py` exists with:

```python
"""add roles column to sessions

Revision ID: 0003_session_roles
Revises: 0002_add_books
Create Date: 2026-05-21 ...

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401 — match 0002's import style for autogenerate parity
from alembic import op

revision: str = "0003_session_roles"
down_revision: str | Sequence[str] | None = "0002_add_books"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add `sessions.roles` (NOT NULL, default ''). Story 7.1 — ACME-TS P4."""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "roles",
                sa.String(),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    """Drop `sessions.roles`."""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("roles")
```

The `server_default=""` is **required** because SQLite cannot ALTER TABLE to add a NOT NULL column without one (the `op.batch_alter_table` context manager handles the table-recreate dance under SQLite — same pattern Alembic uses by default; do NOT switch to raw `op.add_column` here).

**And** `services/bff/src/bff/services/session_service.py:create_session` gains a new keyword parameter (call sites updated by AC4):

```python
async def create_session(
    self,
    db: AsyncSession,
    *,
    sub: str,
    access_token: str,
    refresh_token: str,
    id_token: str,
    expires_at: datetime,
    roles: frozenset[Role],   # NEW — Story 7.1 AC3
) -> entities.Session:
```

…and the `entities.Session(...)` constructor call inside the retry loop persists `roles=",".join(sorted(role.value for role in roles))`. The empty-set case correctly produces `""`.

**And** the migration is autogenerable: running `cd services/bff && uv run alembic revision --autogenerate -m "add roles column to sessions"` on a clean DB at HEAD `0002_add_books` produces a migration whose diff matches the file above (modulo timestamp + revision id). The dev agent may either hand-write the migration verbatim from this AC or autogenerate-then-rename.

> **Failure-prevention note (no enum column type):** SQLAlchemy supports `sa.Enum(Role)` for native enum columns, but: (a) we have **multiple** roles per session (the comma-join), and (b) the empty-string sentinel doesn't map cleanly to a one-of-N enum. Stick with `sa.String()` — the wire/DB encoding is `"admin,reader"` (alphabetically sorted; see AC3's `",".join(sorted(...))`), the in-memory shape is `frozenset[Role]`, and the boundary in both directions lives in `session_service.py`.

> **Failure-prevention note (sorted before join):** The sort is for **DB-roundtrip determinism**, not for any wire contract — but it pays off in tests (`assert row.roles == "admin,reader"`) and in any future "did the role set change between sessions" diff. Don't drop the `sorted(...)`.

> **Failure-prevention note (don't add an index):** No `index=True` on the new column. Roles are read along with the session row (always by `Session.id` PK), never queried by role. An index would be pure overhead.

### AC4 — Two new endpoints: `GET /api/me/roles` and `GET /api/admin/ping`

**Given** the BFF API surface at `services/bff/src/bff/api/`,
**When** the developer inspects the post-Story-7.1 source tree,
**Then** two new endpoints exist:

**4a. `GET /api/me/roles`** — added to `services/bff/src/bff/api/me.py` alongside the existing `/api/me`:

- **Auth:** requires a valid session cookie. Missing / unknown / expired session → 401 with the canonical `session_expired` envelope (identical to `/api/me`'s 401 shape — see `me.py:36–44`).
- **Success:** 200 + JSON `{"roles": [...]}` where the value is a **sorted list of strings**, e.g. `{"roles": ["reader"]}` or `{"roles": ["admin", "reader"]}`. (Returning a list — not a set — is the JSON-encoding constraint; sort order is deterministic for assertion stability.)
- **Source:** the response is derived from the persisted `session_row.roles` string (split on `","`, filter empties). The endpoint does **NOT** re-decode the id_token and re-run `map_claims_to_roles` — the mapping happened once at `/auth/callback` time (AC4c) and the persisted column is the runtime source of truth.

**4b. `GET /api/admin/ping`** — added in a new file `services/bff/src/bff/api/admin.py`:

- **Auth:** requires a valid session cookie. Missing / unknown / expired session → 401 `session_expired` (same envelope as 4a).
- **Authorization:** the session's `roles` string must contain `Role.ADMIN.value`. If not, 403 with the canonical envelope:
  ```json
  {
    "errorCode": "FORBIDDEN",
    "message": "Access forbidden",
    "detail": null
  }
  ```
  — reuses the **existing** `ErrorCode.FORBIDDEN` (`services/bff/src/bff/core/errors.py:18`). Do **NOT** add a new `ErrorCode.FORBIDDEN_SCOPE` to the BFF; that code is RS-only (`services/resource-server/src/resource_server/core/errors.py:32`) and inventing a BFF parallel for a one-off demo endpoint would muddle the contract documented in `docs/security-review.md` §5. The planning spec at commit `760cbb2` mis-stated "reuses existing `FORBIDDEN_SCOPE`"; that's wrong and is corrected here.
- **Success:** 200 + JSON `{"ok": true}`. No other fields. The endpoint is deliberately trivial — its purpose is to prove the role-gating wiring works end-to-end, not to do real work.

**4c. `/auth/callback` plumbs the mapped roles into `create_session(...)`.** Edit `services/bff/src/bff/api/auth.py:auth_callback` (currently around lines 272–279):

- After `verify_id_token(...)` returns the claims dict (call it `claims`), call `from bff.auth.role_mapping import map_claims_to_roles; roles = map_claims_to_roles(claims)` and pass `roles=roles` to `_session_service.create_session(...)`.
- The import goes at the top of the file alongside the existing `bff.auth.keycloak_cookie_session` imports (alphabetical block ordering — `role_mapping` sorts after `keycloak_cookie_session`).
- No other change to `auth_callback` — the rest of the handler (cookie setting, redirect to `return_to`, the safe-session-id logging) stays byte-identical.

**4d. Router registration.** `services/bff/src/bff/main.py` gains one new include after the existing `me_router` line:

```python
from bff.api.admin import router as admin_router
...
app.include_router(admin_router)
```

…and the new `/api/me/roles` endpoint lives on the existing `me_router` so no second `include_router` call is needed for it.

> **Failure-prevention note (don't share a router prefix):** Do **NOT** put `/api/me/roles` on a new `api/me_roles.py` file with a separate router — that would force a second `include_router` and re-establish the session-cookie-resolution dance for no benefit. Add it to `me.py` and reuse the same `_session_service.get_session(...)` + `_as_utc_aware(...)` + `_session_expired_response()` helpers already in the file.

> **Failure-prevention note (admin.py NOT under /v1):** `/api/admin/ping` is NOT a domain resource (no `/v1/admin/...`). Mount it on a freestanding `APIRouter()` (no `prefix=`) and let the route decorator carry the full path. Mirrors how `me.py:51` declares `@router.get("/api/me")` directly.

> **Failure-prevention note (the 403 happens BEFORE any business logic):** In `admin.py`, the order of checks inside the handler is: (1) session cookie present? else 401; (2) session row exists + not expired? else 401 (with lazy-delete on expired); (3) `Role.ADMIN.value in row.roles.split(",")`? else 403; (4) finally, return `{"ok": true}`. The 401 must always precede the 403 — otherwise an unauthenticated caller can probe whether `/api/admin/*` exists, which leaks the admin surface. (Compare `services/resource-server/src/resource_server/auth/oidc_bearer.py:130` — RS scope enforcement is identical: 401 first, 403 only after the token is verified.)

> **Failure-prevention note (no scope on the session-cookie path):** The new endpoints are **BFF-native** authZ; they do NOT involve calling the Resource Server. There is no `access_token` round-trip, no `require_scope`, no `RsUnavailable` handling. Don't import `resource_server_client` in `admin.py`.

### AC5 — Tests

**Given** the BFF test suite at `services/bff/tests/`,
**When** `cd services/bff && uv run pytest -x -q` runs,
**Then** the suite is green AND covers the following:

**5a. `tests/auth/test_role_mapping.py` (NEW)** — unit tests for `bff.auth.role_mapping`. Required test cases:

1. `test_empty_groups_claim_returns_empty_set` — `claims = {"groups": []}` → `frozenset()`.
2. `test_missing_groups_claim_returns_empty_set` — `claims = {}` → `frozenset()`.
3. `test_unknown_group_only_returns_empty_set` — `claims = {"groups": ["nope"]}` → `frozenset()`.
4. `test_reader_only_returns_reader_role` — `claims = {"groups": ["reader"]}` → `frozenset({Role.READER})`.
5. `test_reader_and_admin_returns_both_roles` — `claims = {"groups": ["reader", "admin"]}` → `frozenset({Role.READER, Role.ADMIN})`.
6. `test_admin_only_returns_admin_role` — `claims = {"groups": ["admin"]}` → `frozenset({Role.ADMIN})`.
7. `test_non_list_groups_claim_returns_empty_set` — `claims = {"groups": "reader"}` (string, not list) → `frozenset()`. (Defensive — a misconfigured realm or a future single-group mapper.)
8. `test_non_string_element_is_silently_dropped` — `claims = {"groups": ["reader", 42, None, "admin"]}` → `frozenset({Role.READER, Role.ADMIN})`.
9. `test_unknown_mixed_with_known_drops_unknown` — `claims = {"groups": ["reader", "superadmin", "admin"]}` → `frozenset({Role.READER, Role.ADMIN})`.
10. `test_role_enum_values_match_realm_short_names` — assert `Role.READER.value == "reader"` and `Role.ADMIN.value == "admin"`. (Pin-test: the realm config (AC1) and the enum must stay in lockstep; this test catches drift if either is edited without the other.)
11. `test_module_purity_no_orm_imports` — programmatic import-check: `import importlib, sys; m = importlib.import_module("bff.auth.role_mapping"); assert not any(name.startswith("sqlalchemy") or name.startswith("sqlmodel") for name in sys.modules if name in m.__dict__.values())` — or equivalent. The intent is to fail loud if a future refactor leaks an ORM import into the mapper.

Coverage of `services/bff/src/bff/auth/role_mapping.py` MUST be ≥ 90% lines (the file has roughly 8 executable lines after docstrings; the test cases above hit every branch).

**5b. `tests/api/test_admin.py` (NEW)** — integration tests for `GET /api/admin/ping`, using the existing test client + DB-fixture pattern (mirrors `tests/api/test_me.py`). Required test cases:

1. `test_admin_ping_returns_200_for_session_with_admin_role` — seed a session with `roles="admin,reader"` (freshuser case); GET `/api/admin/ping` with the session cookie → 200 `{"ok": true}`.
2. `test_admin_ping_returns_403_for_session_without_admin_role` — seed a session with `roles="reader"` (testuser case); GET → 403 `{"errorCode": "FORBIDDEN", "message": "Access forbidden", "detail": null}`.
3. `test_admin_ping_returns_403_for_session_with_no_roles` — seed a session with `roles=""`; GET → 403 (same envelope as 2). Belt-and-suspenders: a session predating Story 7.1 (i.e. with the migration's `server_default=""`) should NOT be implicitly admin.
4. `test_admin_ping_returns_401_for_missing_session_cookie` — no `bff_session` cookie; GET → 401 `{"errorCode": "session_expired", ...}`.
5. `test_admin_ping_returns_401_for_unknown_session_id` — cookie present but no matching row; GET → 401.
6. `test_admin_ping_returns_401_for_expired_session` — seed a row whose `expires_at` is 1 minute in the past; GET → 401, and the row is lazily deleted (assert via `await db.get(Session, sid) is None` after the request).
7. `test_admin_ping_401_precedes_403` — seed NO session row but pass a cookie that *looks* like a valid id; GET → 401 (not 403). Pin-test for the AC4 ordering invariant.

**5c. `tests/api/test_me.py` (EDIT)** — add cases for `GET /api/me/roles`:

1. `test_me_roles_returns_200_with_admin_and_reader` — seed `roles="admin,reader"`; GET `/api/me/roles` → 200 `{"roles": ["admin", "reader"]}`.
2. `test_me_roles_returns_200_with_empty_list_when_no_roles` — seed `roles=""`; GET → 200 `{"roles": []}`.
3. `test_me_roles_returns_200_with_single_role` — seed `roles="reader"`; GET → 200 `{"roles": ["reader"]}`.
4. `test_me_roles_returns_401_for_missing_session_cookie` — no cookie; GET → 401 (same envelope as `/api/me`).
5. `test_me_roles_returns_401_for_expired_session` — expired row; GET → 401 + lazy-delete.

**5d. `tests/services/test_session_service.py` (EDIT)** — extend the `create_session` cases:

1. Existing `test_create_session_persists_row` test gains a `roles=frozenset()` kwarg (default empty); assert the persisted row has `row.roles == ""`.
2. New `test_create_session_persists_sorted_role_string` — `roles=frozenset({Role.ADMIN, Role.READER})`; assert `row.roles == "admin,reader"` (sorted, comma-joined).
3. New `test_create_session_with_admin_only` — `roles=frozenset({Role.ADMIN})`; assert `row.roles == "admin"`.

**5e. `tests/api/test_auth.py` (EDIT)** — the `_complete_login` helper / callback happy-path test gains an assertion that the persisted `Session.roles` reflects the synthetic IdP's id_token `groups` claim. Specifically:

1. The synthetic IdP at `tests/auth/synthetic_idp.py` gains a `groups` field in the id_token claims it mints (default `[]` for backwards-compat with existing tests; the new tests pass an explicit `groups=["reader", "admin"]` kwarg).
2. The existing `auth_callback_happy_path` test asserts `session_row.roles == ""` (no groups in the default minted claims — proves the empty-set path).
3. A new `test_auth_callback_persists_mapped_roles_from_groups_claim` — mint claims with `groups=["reader", "admin"]`; complete the callback; assert `session_row.roles == "admin,reader"`. This is the **end-to-end** wiring proof inside the BFF: realm-mapper claim → callback → mapper → session row.

**5f. Existing test green-bar.** All pre-Story-7.1 tests under `services/bff/tests/` continue to pass with zero edits (apart from the surgical additions in 5c/5d/5e above). The Story 1.5 `test_keycloak_cookie_session.py` is **NOT** edited; the `oidc_bearer` and `csrf` modules are **NOT** touched. The Story 2.2 books tests are **NOT** touched.

**5g. Migration round-trip.** `cd services/bff && uv run alembic upgrade head` from a fresh DB lands at `0003_session_roles`; `uv run alembic downgrade -1` returns to `0002_add_books` without errors. (No test required beyond the dev agent manually verifying with a throwaway SQLite file; the integration tests' `SQLModel.metadata.create_all` path exercises the model schema directly and skips Alembic.)

> **Failure-prevention note (don't rewrite the synthetic IdP claim signature):** AC5e changes the synthetic IdP's minted id_token to optionally carry `groups` — make this **additive only**. Existing tests that don't pass `groups=` get `groups=[]` injected and continue to assert `row.roles == ""`. Breaking the synthetic-IdP signature is a Story-1.5-regression magnet.

### AC6 — End-to-end manual verification (curl)

**Given** a clean `docker compose --profile default up --build -d` against the post-Story-7.1 baseline,
**When** the developer (or operator) walks through these curl steps from the host,
**Then** all responses match the table below.

1. Log in as `freshuser`:
   ```sh
   # Boot a session via the OAuth flow. This is the manual curl-equivalent of
   # Mode-B HTTP probes documented in docs/smoke-run.md (Story 5.4).
   # Use the SPA at http://localhost:4000 + a real browser, then grab the
   # session cookie from devtools.
   ```
2. With the freshuser session cookie:
   ```sh
   curl -s -b "bff_session=<COOKIE>" http://localhost:4000/api/me/roles
   # Expected: HTTP 200, body: {"roles":["admin","reader"]}

   curl -s -b "bff_session=<COOKIE>" http://localhost:4000/api/admin/ping
   # Expected: HTTP 200, body: {"ok":true}
   ```
3. Log out (`POST /auth/logout`) and log back in as `testuser`. With the testuser session cookie:
   ```sh
   curl -s -b "bff_session=<COOKIE>" http://localhost:4000/api/me/roles
   # Expected: HTTP 200, body: {"roles":["reader"]}

   curl -i -s -b "bff_session=<COOKIE>" http://localhost:4000/api/admin/ping
   # Expected: HTTP 403, body: {"errorCode":"FORBIDDEN","message":"Access forbidden","detail":null}
   ```
4. Without any cookie:
   ```sh
   curl -i -s http://localhost:4000/api/admin/ping
   # Expected: HTTP 401, body: {"errorCode":"session_expired",...}
   curl -i -s http://localhost:4000/api/me/roles
   # Expected: HTTP 401, body: {"errorCode":"session_expired",...}
   ```

**And** the four expectations above are recorded in the story's Completion Notes block as a Mode-B (programmatic) walk-through transcript at dev-close. Mode-A (human-in-browser) is **not required** for this story — the demo is a backend-only surface; no UI is added. (A future SPA follow-up could surface "🛡️ Admin: yes/no" in TopChrome — recorded as a **deferred** item in Completion Notes if 7.1 lands without UI.)

> **Failure-prevention note (host port :4000):** Post-Epic-6 the public edge is the SPA SSR Node container at `:4000`, which reverse-proxies `/api/*` and `/auth/*` to the BFF. The BFF is no longer published on `:8000` (Story 6.2). Curl through `:4000`, not `:8000`.

### AC7 — Coverage targets

**Given** Story 5.1's per-file BFF coverage floor (≥70% lines per file; ≥90% aggregate),
**When** `cd services/bff && uv run pytest --cov=src --cov-report=term-missing` runs at story close,
**Then**:

- `bff/auth/role_mapping.py` is ≥90% lines (the file is ~10 executable lines; AC5a's 11 tests should hit every branch).
- `bff/api/admin.py` is ≥85% lines (the file is ~30 executable lines covering the 401/403/200 paths; AC5b's 7 tests cover all branches except the unreachable `RuntimeError` if any).
- `bff/api/me.py` aggregate stays ≥80% lines (it grew by the `/api/me/roles` handler; AC5c adds 5 tests).
- `bff/services/session_service.py` aggregate stays ≥90% lines (it grew by one kwarg; AC5d adds 2 tests).
- BFF aggregate line coverage stays at or above Story 5.1's attested 97.26% **after subtracting** the PKCE-removal delta (PKCE deletion removed ~10 source lines; Story 7.1 adds ~50 source lines net; aggregate should land within ±1 percentage point of Story 5.1's attestation).

### AC8 — Scope-leak audit (load-bearing close gate)

**Given** the story's Scope section above declares "four directories only,"
**When** the developer runs `git status --short` immediately before requesting code review,
**Then** the file list contains entries **only** under:

- `keycloak/realm-bmad-books.json`
- `services/bff/src/bff/auth/role_mapping.py` (`A`)
- `services/bff/src/bff/api/admin.py` (`A`)
- `services/bff/src/bff/api/me.py` (`M`)
- `services/bff/src/bff/api/auth.py` (`M`)
- `services/bff/src/bff/main.py` (`M`)
- `services/bff/src/bff/models/entities/session.py` (`M`)
- `services/bff/src/bff/services/session_service.py` (`M`)
- `services/bff/alembic/versions/0003_session_roles.py` (`A`)
- `services/bff/tests/auth/test_role_mapping.py` (`A`)
- `services/bff/tests/api/test_admin.py` (`A`)
- `services/bff/tests/api/test_me.py` (`M`)
- `services/bff/tests/api/test_auth.py` (`M`)
- `services/bff/tests/auth/synthetic_idp.py` (`M`)
- `services/bff/tests/services/test_session_service.py` (`M`)
- `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md` (this story file — `M`)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (`M`)
- optionally `_bmad-output/implementation-artifacts/deferred-work.md` (only if new D-IDs are logged)

**And** the following directories have **zero** entries: `services/resource-server/`, `spa/`, `e2e/`, `compose/`, `docs/`, `_bmad-output/planning-artifacts/`, `README.md`, `.env.example`, top-level `docker-compose.yml`, `Justfile`, `.dockerignore`.

## Tasks / Subtasks

- [ ] **Task 1 — Realm changes** (AC: 1)
  - [ ] 1.1 Add `"groups": [{"name": "reader", "path": "/reader"}, {"name": "admin", "path": "/admin"}]` to `keycloak/realm-bmad-books.json`.
  - [ ] 1.2 Add the `oidc-group-membership-mapper` protocolMapper to the `bmad-books-bff` client's `protocolMappers` array (`full.path: "false"`, claim name `"groups"`, id_token + access_token on, userinfo off).
  - [ ] 1.3 Add `"groups": ["/reader"]` to the testuser user definition.
  - [ ] 1.4 Add `"groups": ["/reader", "/admin"]` to the freshuser user definition.
  - [ ] 1.5 Verify `docker compose up keycloak --force-recreate` imports cleanly (no `RealmImportProvider` warnings about the new fields).

- [ ] **Task 2 — `role_mapping.py` module** (AC: 2)
  - [ ] 2.1 Create `services/bff/src/bff/auth/role_mapping.py` with the `Role` StrEnum + `map_claims_to_roles(...)` function exactly as specified in AC2.
  - [ ] 2.2 Verify the module has **no** imports outside `collections.abc`, `enum`, `typing`.
  - [ ] 2.3 (Optional) Re-export from `bff.auth.__init__` if symmetry with other auth-module exports is desired — but only if the existing `__init__` already re-exports; do NOT add a re-export pattern that didn't exist before.

- [ ] **Task 3 — `Session.roles` column** (AC: 3)
  - [ ] 3.1 Add the `roles: str = Field(default="", nullable=False)` line to `services/bff/src/bff/models/entities/session.py` (immediately after `csrf_secret` for diff-locality).
  - [ ] 3.2 Hand-write `services/bff/alembic/versions/0003_session_roles.py` using the AC3 template (do NOT rely on autogenerate alone — verify the diff matches).
  - [ ] 3.3 Verify migration round-trip: `uv run alembic upgrade head` → `uv run alembic downgrade -1` → `uv run alembic upgrade head` on a throwaway SQLite file.

- [ ] **Task 4 — `SessionService.create_session(...)` kwarg** (AC: 3)
  - [ ] 4.1 Add the `roles: frozenset[Role]` kwarg to `create_session` (no default — caller MUST pass; the AC4c edit to `auth_callback` is the load-bearing caller).
  - [ ] 4.2 In the retry loop, set `roles=",".join(sorted(r.value for r in roles))` on the `entities.Session(...)` constructor call.
  - [ ] 4.3 Update the existing `test_session_service.py` cases that call `create_session(...)` to pass `roles=frozenset()` (default-empty); see AC5d.
  - [ ] 4.4 Add `from bff.auth.role_mapping import Role` to `session_service.py`. Position it in the existing alphabetical `from bff...` import block.

- [ ] **Task 5 — `/api/me/roles` endpoint** (AC: 4a, 5c)
  - [ ] 5.1 In `services/bff/src/bff/api/me.py`, add a new handler `@router.get("/api/me/roles")` that mirrors the existing `me(...)` handler's session-cookie + lazy-cleanup pattern (lines 51–86). Reuse `_session_expired_response()` and `_as_utc_aware()` verbatim.
  - [ ] 5.2 Derive the response from `row.roles.split(",")` filtered for empties; return `JSONResponse(200, {"roles": sorted(roles_list)})`.

- [ ] **Task 6 — `admin.py` router + `/api/admin/ping`** (AC: 4b, 4d, 5b)
  - [ ] 6.1 Create `services/bff/src/bff/api/admin.py`. Follow the import + scaffolding pattern of `services/bff/src/bff/api/me.py` (no `prefix=`; freestanding `APIRouter(tags=["Admin"])`; module-level `_session_service`).
  - [ ] 6.2 Implement `GET /api/admin/ping` with the strict 401-before-403 ordering (AC4 failure-prevention note).
  - [ ] 6.3 Use `ErrorCode.FORBIDDEN` (existing, no new error code) for the 403 envelope. Build the JSON response inline (mirrors `_session_expired_response()` shape) rather than raising `AppException` — the file already inlines the 401 path, keep the 403 in the same idiom.
  - [ ] 6.4 In `services/bff/src/bff/main.py`, add `from bff.api.admin import router as admin_router` (alphabetically in the existing `from bff.api.* import router as ..._router` block) and `app.include_router(admin_router)` after `app.include_router(me_router)`.

- [ ] **Task 7 — `/auth/callback` plumbs the mapped roles** (AC: 4c)
  - [ ] 7.1 In `services/bff/src/bff/api/auth.py`, add the import `from bff.auth.role_mapping import map_claims_to_roles` (in the existing `from bff.auth.* import ...` block — alphabetically after `keycloak_cookie_session`).
  - [ ] 7.2 In `auth_callback(...)` after `claims = verify_id_token(...)`, compute `roles = map_claims_to_roles(claims)` and pass it to `_session_service.create_session(..., roles=roles)`.

- [ ] **Task 8 — Tests** (AC: 5, 7)
  - [ ] 8.1 Create `services/bff/tests/auth/test_role_mapping.py` with the 11 unit tests from AC5a.
  - [ ] 8.2 Create `services/bff/tests/api/test_admin.py` with the 7 integration tests from AC5b. Use the existing test-client + DB fixture pattern from `services/bff/tests/api/test_me.py` (parametrize the cookie + DB-seeded session).
  - [ ] 8.3 Edit `services/bff/tests/api/test_me.py` to add the 5 `/api/me/roles` cases from AC5c.
  - [ ] 8.4 Edit `services/bff/tests/services/test_session_service.py` to add the 2 new cases from AC5d and update the existing `create_session` case to pass `roles=frozenset()`.
  - [ ] 8.5 Edit `services/bff/tests/auth/synthetic_idp.py` to accept a `groups` kwarg on the id-token claims minter (default `[]`); edit `services/bff/tests/api/test_auth.py` per AC5e.
  - [ ] 8.6 Run `uv run pytest -x -q` and verify the full suite is green.
  - [ ] 8.7 Run `uv run pytest --cov=src --cov-report=term-missing` and verify the AC7 thresholds.

- [ ] **Task 9 — Manual curl walk-through** (AC: 6)
  - [ ] 9.1 `docker compose --profile default up --build -d`; wait for healthchecks.
  - [ ] 9.2 Log in as freshuser (via browser at `http://localhost:4000`); copy `bff_session` cookie.
  - [ ] 9.3 Execute the 4 curl calls; capture the HTTP status + body for each; paste into Completion Notes.
  - [ ] 9.4 Log out, log in as testuser, repeat the testuser-half of the table.
  - [ ] 9.5 Repeat the no-cookie pair.
  - [ ] 9.6 `docker compose down` (without `-v` — preserve volumes for any operator follow-up).

- [ ] **Task 10 — Quality gates** (AC: all)
  - [ ] 10.1 `cd services/bff && uv run ruff check && uv run ty` clean.
  - [ ] 10.2 `git status --short` matches the AC8 file list **exactly** (no extra surfaces, no missing surfaces).
  - [ ] 10.3 Update sprint-status.yaml: this story `ready-for-dev` → `in-progress` (at dev-start) → `review` (at dev-complete). Epic 7 `backlog` → `in-progress` was already flipped at create-story time.
  - [ ] 10.4 Update this story file's frontmatter `status: ready-for-dev` → `review` and append Completion Notes (with the curl transcripts from Task 9).

## Dev Notes

### Source-tree map (read-only / write-only)

**Files this story creates (5):**
- `services/bff/src/bff/auth/role_mapping.py`
- `services/bff/src/bff/api/admin.py`
- `services/bff/alembic/versions/0003_session_roles.py`
- `services/bff/tests/auth/test_role_mapping.py`
- `services/bff/tests/api/test_admin.py`

**Files this story modifies (10):**
- `keycloak/realm-bmad-books.json` — add `"groups"` array + group-mapper + user memberships.
- `services/bff/src/bff/models/entities/session.py` — add `roles` column.
- `services/bff/src/bff/services/session_service.py` — new `roles` kwarg on `create_session`.
- `services/bff/src/bff/api/me.py` — add `/api/me/roles` handler.
- `services/bff/src/bff/api/auth.py` — plumb `map_claims_to_roles(...)` into `auth_callback`.
- `services/bff/src/bff/main.py` — register `admin_router`.
- `services/bff/tests/api/test_me.py` — add 5 `/api/me/roles` cases.
- `services/bff/tests/services/test_session_service.py` — add 2 cases + update 1.
- `services/bff/tests/auth/synthetic_idp.py` — accept `groups` kwarg (additive).
- `services/bff/tests/api/test_auth.py` — assert persisted roles on callback happy-path.

**Files this story MUST NOT modify (load-bearing constraints — failing this is a code-review-pass blocker):**
- Anything under `services/resource-server/` — the RS keeps scope-based enforcement; no `Role` concept enters it.
- Anything under `spa/` — no UI changes; the demo is curl-only.
- Anything under `e2e/` — no new Playwright specs.
- Anything under `compose/`, top-level `docker-compose.yml`, `.env.example`, `.dockerignore`, `Justfile`.
- Anything under `docs/` — no security-review / coverage-report / smoke-run / README edits.
- Anything under `_bmad-output/planning-artifacts/` — PRD / architecture / epics stay byte-identical (the Sprint Change Proposal at `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` is the source of truth for the principle; no architecture amendment is needed for Story 7.1 itself).
- The existing `services/bff/alembic/versions/0001_init_init_sessions_and_auth_states.py` and `0002_add_books.py` — they are historical; Story 7.1's migration is purely additive at `0003`.
- The `bff.auth.csrf` module, the `bff.auth.keycloak_cookie_session` module (apart from the AC4c top-of-file import addition is in `bff.api.auth` not in `bff.auth`).
- `services/bff/src/bff/api/books.py`, `services/bff/src/bff/api/reading_speed.py`, `services/bff/src/bff/api/test_reset.py`, `services/bff/src/bff/api/health.py`, `services/bff/src/bff/api/v1.py`.

### Reading-from-existing-code pointers (read these before coding)

The story repeatedly mirrors patterns established in earlier stories. The dev agent should *read*, not reinvent:

| Concern | Existing implementation | Use it for |
|---|---|---|
| Session-cookie resolution + lazy-cleanup | `services/bff/src/bff/api/me.py:51–86` | The 401 path in `admin.py` and `/api/me/roles`. |
| ErrorCode envelope shape | `services/bff/src/bff/core/errors.py:9–47` + `build_error_body(...)` | The 403 envelope. Reuse `ErrorCode.FORBIDDEN`. |
| Alembic `op.batch_alter_table` under SQLite | `services/bff/alembic/versions/0002_add_books.py` is a `create_table`, not an `alter_table`, so it doesn't directly model 7.1's case — but it shows the autogenerate-clean style. The `batch_alter_table` pattern is the SQLite-compatible idiom for ALTER TABLE ADD COLUMN with a NOT NULL default; see Alembic docs ([alembic.sqlalchemy.org/en/latest/batch.html](https://alembic.sqlalchemy.org/en/latest/batch.html)). | Story 7.1's `0003_session_roles.py`. |
| Synthetic-IdP id-token minting | `services/bff/tests/auth/synthetic_idp.py` (post-`760cbb2` state: `code_verifier` kwarg kept as no-op for back-compat). | AC5e — add `groups` as a similarly-additive kwarg. |
| Router registration pattern | `services/bff/src/bff/main.py:8–11` | AC4d — add `admin_router`. |
| Test-client + DB-seeded session fixture | `services/bff/tests/api/test_me.py` (the cookie-seed + DB-row-create pattern at the top of the file's test cases). | AC5b — `test_admin.py` integration tests. |

### Pre-existing architectural decisions Story 7.1 honors

- **A1 (BFF as OIDC client):** Story 7.1 doesn't alter the OIDC flow; the mapper is downstream of `verify_id_token(...)`.
- **A3 (`auth_states` storage):** Untouched. The `auth_states` table doesn't gain a roles column — roles are bound to a *session*, not an auth-state.
- **A8 (CSP source moved to SPA edge in Epic 6):** Untouched. `admin.py` is a JSON-only endpoint, no CSP concerns.
- **C5 (ErrorCode envelope):** Reused. No new ErrorCode.
- **I3 (Keycloak realm-as-code):** Extended (the `groups` array + group-mapper) but the existing client-attributes / users / scopes structure is preserved.
- **Pattern Amendments — 2026-05-21 PKCE removal:** assumed baseline (see Prerequisites).

### Why no SPA changes

The PRD §5 single-role product design means there's no real product surface to gate on roles. A toy "Admin: yes/no" badge in TopChrome would be illustrative but adds three layers of optionality (an `/api/me/roles` SPA service call, an interceptor for SSR, a TopChrome conditional render — all of which would force Playwright spec edits + SSR transfer-state considerations). The decision recorded at create-story time is: **no SPA work in 7.1**. A follow-up story (Epic 7 story 7.4, not yet drafted) could add the UI surface if the user requests it post-merge.

### Why no e2e / Playwright spec

The demo is curl-exercisable end-to-end; the realm change is forward-compatible with the existing J1 spec (testuser still logs in, `/api/me` still returns `{sub, preferred_username}` — the new `groups` claim is silently ignored by every existing surface). Adding a Playwright spec would force a J6-style scaffolding (kill RS / etc.) without product value. Recorded as **explicit non-scope** above.

### Why this story is independent of 7.2 and 7.3

- **7.2 (OIDC discovery bootstrap):** changes how the BFF and RS *load* their OIDC config at startup (`.well-known/openid-configuration` fetch + cache). Story 7.1 doesn't touch startup; it operates entirely at request time. No file overlap.
- **7.3 (Structured auth-decision logs):** introduces a logger helper for `{timestamp, sub, decision, reason}` records and converts ~12 existing call sites. Story 7.1's mapper is **explicitly silent** (see AC2's note on why) — the 7.3 helper is not a dependency. If 7.3 lands first, Story 7.1 *may* add one log line at the `/api/admin/ping` 403 path; if 7.3 lands later, that log line gets added then. Either order works.

### Project Structure Notes

- All new BFF files live in their canonical mirror paths (`src/bff/auth/role_mapping.py` ↔ `tests/auth/test_role_mapping.py`; `src/bff/api/admin.py` ↔ `tests/api/test_admin.py`) per the architecture's "tests mirror source path" convention (architecture.md §"Implementation Patterns" line 860 — "A backend test under tests/utils/ for code that lives in src/<svc>/services/ — must mirror source path").
- The Alembic version file numbering is **0003**, not 0002 (the original planning spec at commit `760cbb2` mis-said "0002_session_roles"; `0002_add_books` already exists; honest correction recorded here).
- No new dependencies (`uv add ...`) — the story uses only the stdlib + already-present libs (FastAPI, SQLModel, Alembic, pytest, PyJWT, httpx).

### References

- **Sprint Change Proposal** (introduces Epic 7): `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §1 (P4 framing), §4 Group I (Story 7.1 sketch), §5 (Future work table).
- **Original planning spec** (committed in `760cbb2`): `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md` @ HEAD `simplified-implementation` — provides the original 5 ACs + Dependencies + Notes blocks; this story file is a **superset**, correcting the two factual errors (FORBIDDEN_SCOPE reuse claim; migration numbering 0002 → 0003) and adding the test-case enumeration + curl walk-through + scope-leak audit.
- **PRD §5 — Single-role product design**: `_bmad-output/planning-artifacts/PRD.md` — the reason this story is "architectural illustration" not "product feature."
- **Architecture Pattern Amendments — 2026-05-21**: `_bmad-output/planning-artifacts/architecture.md:863–866` — the post-`760cbb2` baseline state (PKCE removed; assumed by this story).
- **BFF `/api/me`** (the pattern this story extends): `services/bff/src/bff/api/me.py`.
- **BFF `auth_callback`** (where `map_claims_to_roles(...)` plugs in): `services/bff/src/bff/api/auth.py:172–316`.
- **BFF `Session` model** (gains `roles` column): `services/bff/src/bff/models/entities/session.py`.
- **BFF `SessionService.create_session`** (gains `roles` kwarg): `services/bff/src/bff/services/session_service.py:134–173`.
- **BFF `ErrorCode.FORBIDDEN`** (reused for the 403): `services/bff/src/bff/core/errors.py:18`.
- **RS `ErrorCode.FORBIDDEN_SCOPE`** (NOT reused; cited only to justify why the BFF doesn't get its own copy): `services/resource-server/src/resource_server/core/errors.py:32`.
- **Keycloak `oidc-group-membership-mapper`** (the realm-side primitive): [keycloak.org/docs/26.x/server_admin/index.html#_protocol-mappers](https://www.keycloak.org/docs/26.x/server_admin/) — search for "Group Membership". Note: the realm-import JSON shape used here matches Keycloak 26's `realm.json` schema; older Keycloak versions used a slightly different `config` key set.
- **Python `StrEnum`** (PEP 663, available 3.11+; Python 3.14 is the project's pinned version): [docs.python.org/3.14/library/enum.html#enum.StrEnum](https://docs.python.org/3.14/library/enum.html#enum.StrEnum).
- **Alembic `batch_alter_table` under SQLite**: [alembic.sqlalchemy.org/en/latest/batch.html](https://alembic.sqlalchemy.org/en/latest/batch.html).

## Definition of Done

The story is `done` when **all** of:

1. AC1–AC8 each verifiable by a code-review reader running the commands embedded in the ACs.
2. `cd services/bff && uv run pytest -x -q` is green.
3. `cd services/bff && uv run pytest --cov=src` meets the AC7 thresholds.
4. `cd services/bff && uv run ruff check && uv run ty` clean.
5. `git status --short` matches the AC8 allowlist exactly.
6. The Mode-B curl walk-through (AC6) transcript is recorded in this story's Completion Notes block.
7. This story's frontmatter `status` is flipped to `review` and the sprint-status.yaml entry is flipped from `in-progress` to `review`.
8. **No** regression in any previously-passing test under `services/bff/tests/`, `services/resource-server/tests/`, `spa/`, or `e2e/`.
9. The 4 verification steps documented in `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §5 ("Pending verification") have either been re-run **OR** the dev agent has confirmed in Completion Notes that the post-`760cbb2` baseline is intact (BFF test suite green, J1 Playwright passes, realm import clean, `docker compose up` green) — Story 7.1's changes are forward-compatible with all four.
10. (Optional) Any newly-discovered deferred items logged in `_bmad-output/implementation-artifacts/deferred-work.md` with sequential D-IDs continuing from the current max.

## Failure-prevention checklist (review before requesting code-review)

- [ ] **#1 — No new `FORBIDDEN_SCOPE` on the BFF.** The 403 reuses existing `ErrorCode.FORBIDDEN`. (Re-read the planning spec — its "reuse `FORBIDDEN_SCOPE`" wording is wrong.)
- [ ] **#2 — Migration is 0003, not 0002.** `0002_add_books.py` already exists.
- [ ] **#3 — Mapper module is pure.** No `bff.core.*`, no `bff.models.*`, no `sqlalchemy`, no `httpx`. AC5a #11 is the pin-test.
- [ ] **#4 — `groups` claim `full.path: "false"`.** Mapper expects short names, not paths.
- [ ] **#5 — 401 ordering precedes 403** in `admin.py` and `/api/me/roles`. AC5b #7 is the pin-test.
- [ ] **#6 — `roles` column is `nullable=False, default=""` with `server_default=""`** in the migration. Empty-string sentinel, not `NULL`.
- [ ] **#7 — `Session.roles` is comma-joined, sorted, lower-case role values.** Not JSON-encoded, not space-separated, not original-insert-order.
- [ ] **#8 — `/api/me` response is byte-identical.** The new `/api/me/roles` is a **sibling**, not an extension. No SPA / e2e regression possible.
- [ ] **#9 — Synthetic IdP change is additive.** `groups` kwarg defaults to `[]`; all existing tests continue to pass without `groups=` at call sites.
- [ ] **#10 — Zero edits to `services/resource-server/`, `spa/`, `e2e/`, `compose/`, `docs/`, `_bmad-output/planning-artifacts/`.** AC8 scope-leak audit catches violations.
- [ ] **#11 — No `offline_access` reintroduction.** Story 1.5 P3 fix stands.
- [ ] **#12 — Coverage stays at or above Story 5.1's floor.** AC7 thresholds.
- [ ] **#13 — `git status --short` matches the AC8 allowlist.** Run before requesting review.
- [ ] **#14 — Curl walk-through transcript pasted into Completion Notes.** Mode-B 4-call table; freshuser admin=200, testuser admin=403, no-cookie 401×2.
- [ ] **#15 — Worktree baseline is post-`760cbb2`.** If the working tree is behind, rebase / fast-forward before starting. (PKCE-removal commit must be present.)

## Dev Agent Record

### Agent Model Used

(to be filled by dev agent at dev-start)

### Debug Log References

(to be filled by dev agent at dev-time)

### Completion Notes List

(to be filled by dev agent at dev-close — MUST include the AC6 curl walk-through transcript and an explicit confirmation that the AC8 scope-leak audit is clean)

### File List

(to be filled by dev agent at dev-close — MUST exactly match the AC8 allowlist)
