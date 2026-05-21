---
status: done
story_key: 7-1-bff-claim-to-role-mapping-demo
epic: 7
prerequisites: Epic 6 closed (`6-1` / `6-2` / `6-3` / `6-4` all `done`; `epic-6: done`). Story 1.5 has been amended for the post-PKCE confidential-client posture (see Pattern Amendments in `_bmad-output/planning-artifacts/architecture.md` line 863). Keycloak realm in `keycloak/realm-bmad-books.json` already carries the `client_secret_basic` client + the two pre-seeded users (`testuser`, `freshuser`) with no `groups`/role data yet. BFF source at HEAD `760cbb2` has `services/bff/src/bff/models/entities/session.py` (no `roles` column), `services/bff/src/bff/services/session_service.py` (no role plumbing on `create_session`), `services/bff/src/bff/api/auth.py` (callback persists session without roles), and `services/bff/src/bff/core/errors.py` (no `FORBIDDEN_SCOPE` ErrorCode member). Alembic head is `0002_add_books` (NOT `0001_init` — the existing story draft mis-named the new migration as `0002_session_roles`; the correct name in this story is `0003_session_roles`).
supersedes: n/a — this is the first story in Epic 7.
created: 2026-05-21
baseline_commit: 760cbb2
source_of_truth: _bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md §4 Group I + §5 Epic 7 backlog table (P4 row)
---

# Story 7.1: BFF claim-to-role mapping demo (separation of authN/authZ)

Status: done

<!-- Sprint: Epic 7 (ACME-TS Principles Alignment). First story in Epic 7. -->
<!-- Follows: Epic 6 close (Story 6.4 done). -->
<!-- Precedes: Stories 7.2 (OIDC discovery bootstrap) and 7.3 (structured auth-decision logs). -->
<!-- Source of truth: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §4 Group I. -->

## Story

As a reviewer reading this POC as a reference implementation,
I want the BFF to map an OIDC claim (`groups`) to an in-app role and gate at least one endpoint by that role,
so that the POC demonstrates the ACME-TS principle **"the IdP authenticates; the BFF owns role mapping and permissions"** (P4) — even with the project's single-user-domain model — and a future ACME engagement can be pointed at this codebase as the reference for the authN-vs-authZ split.

## Scope (read this first)

Story 7.1 is a **demo + reference-pattern** story. The POC has no product requirement for roles (PRD §5 declares single-role product). The deliverable is **architectural illustration**: a `Role` enum, a pure claim→role mapper, a session column that persists the mapped role set at login, and a single role-gated demo endpoint. The story produces 1 new BFF source module, 1 new Alembic migration, 4 edits across existing BFF source files, 1 edit to the Keycloak realm JSON, 1 new test file, edits to 4 existing test files, and 1 update to the synthetic-IdP harness. No SPA changes are required to satisfy ACs 1–5; an optional SPA badge follow-up is recorded as out-of-scope below.

**Why the Resource Server is untouched:** the RS already enforces *scope*-based authorization on its own endpoints (`require_scope` factory at `services/resource-server/src/resource_server/auth/oidc_bearer.py:130`). This story adds **role-based** enforcement at the BFF as a parallel mechanism. The two layers are complementary, not redundant — the BFF maps claims to roles for endpoints it owns; the RS maps scopes to endpoints it owns. The story does not change the RS contract or behavior in any way.

**Deliverables (12 surfaces, all in `services/bff/` and `keycloak/` unless otherwise noted):**

1. **`keycloak/realm-bmad-books.json`** (MODIFIED) — Add a `"groups"` top-level array declaring two groups (`reader`, `admin`); add `"groups"` to each pre-seeded user (`testuser` → `["reader"]`, `freshuser` → `["reader", "admin"]`); add a new `protocolMapper` of type `oidc-group-membership-mapper` to the `bmad-books-bff` client's existing `protocolMappers` array that injects `groups` into the id_token.
2. **`services/bff/src/bff/auth/role_mapping.py`** (NEW) — declares `class Role(StrEnum)` with members `READER = "reader"` and `ADMIN = "admin"`; declares the pure function `map_claims_to_roles(claims: Mapping[str, Any]) -> frozenset[Role]` that reads the `groups` claim and ignores unknown group names.
3. **`services/bff/src/bff/models/entities/session.py`** (MODIFIED) — Add a `roles: str = Field(default="", nullable=False)` column persisting the comma-separated sorted role list. NOT NULL with `default=""` so a missing-roles login (e.g., a user with no group memberships) is representable.
4. **`services/bff/alembic/versions/0003_session_roles.py`** (NEW) — Alembic migration adding the `roles` column to `sessions` with `nullable=False, server_default=""`. `down_revision = "0002_add_books"`. Note the migration filename: the existing draft AC3 says `0002_session_roles.py` but `0002_add_books.py` already exists at HEAD `760cbb2`; the correct revision name is `0003_session_roles`.
5. **`services/bff/src/bff/services/session_service.py`** (MODIFIED) — `create_session(...)` gains a `roles: frozenset[Role]` keyword argument; persists `",".join(sorted(role.value for role in roles))` into the new column. Existing call sites in `auth.py` updated.
6. **`services/bff/src/bff/api/auth.py`** (MODIFIED) — At the `/auth/callback` token-exchange success path (current lines 245–279), call `map_claims_to_roles(claims)` against the verified id_token claims AFTER `verify_id_token(...)` and BEFORE `_session_service.create_session(...)`; thread the mapped role set into the `create_session(...)` call. Log the role set at INFO at the existing `auth_callback_success` log site (current line 310).
7. **`services/bff/src/bff/api/me.py`** (MODIFIED — NEW endpoints) — Add `GET /api/me/roles` returning `{"roles": ["reader", "admin"]}` (alphabetically sorted) for the current session, 401 `session_expired` if no session. Add `GET /api/admin/ping` returning 200 `{"ok": true}` only if the session's roles include `Role.ADMIN`, otherwise 403 `forbidden_scope`. Both endpoints reuse the existing session-cookie validation pattern at `services/bff/src/bff/api/me.py:51–86`.
8. **`services/bff/src/bff/core/errors.py`** (MODIFIED) — Add `FORBIDDEN_SCOPE = ("forbidden_scope", "Required role missing", 403)` to the `ErrorCode` enum. This member is declared in architecture §C5 (`_bmad-output/planning-artifacts/architecture.md` line 404) but has never been added to the BFF's enum because no BFF endpoint previously needed it; Story 7.1 is the first BFF consumer. The Resource Server already has the equivalent at `services/resource-server/src/resource_server/core/errors.py:32`.
9. **`services/bff/tests/auth/test_role_mapping.py`** (NEW) — Unit tests for the pure mapper. Coverage target ≥90% line per the Story 5.1 per-file floor; the function is short enough that exhaustive parametrization gets 100%. Required cases:
   - empty `claims` dict → `frozenset()`
   - missing `groups` claim → `frozenset()`
   - `{"groups": []}` → `frozenset()`
   - `{"groups": ["unknown"]}` → `frozenset()` (unknown group ignored)
   - `{"groups": ["reader"]}` → `frozenset({Role.READER})`
   - `{"groups": ["reader", "admin"]}` → `frozenset({Role.READER, Role.ADMIN})`
   - `{"groups": ["admin", "reader"]}` → `frozenset({Role.READER, Role.ADMIN})` (order-insensitive)
   - `{"groups": ["reader", "reader"]}` → `frozenset({Role.READER})` (de-dup via set semantics)
   - `{"groups": ["reader", "unknown", "admin"]}` → `frozenset({Role.READER, Role.ADMIN})` (partial-known mix)
   - `{"groups": "reader"}` (claim is a bare string, not a list) → `frozenset()` (defensive — Keycloak emits a list, but a malformed IdP should not crash the BFF; return empty rather than raise)
10. **`services/bff/tests/api/test_admin_ping.py`** (NEW) — Integration tests for `GET /api/admin/ping` and `GET /api/me/roles` using the existing synthetic-IdP harness pattern (Story 1.5 precedent). Required cases:
    - **`/api/admin/ping`** — testuser (only `reader` role) → 403 `forbidden_scope`; freshuser (has `admin`) → 200 `{"ok": true}`; no session cookie → 401 `session_expired`; expired session row → 401 + lazy-delete; unknown session id → 401.
    - **`/api/me/roles`** — testuser → 200 `{"roles": ["reader"]}`; freshuser → 200 `{"roles": ["admin", "reader"]}` (sorted alphabetically); no session → 401 `session_expired`.
    - Use the synthetic IdP's `make_id_token(claims_override={"groups": [...]})` to inject the `groups` claim into the id_token. The harness already supports `claims_override` (see `services/bff/tests/auth/synthetic_idp.py:114`).
11. **`services/bff/tests/auth/synthetic_idp.py`** (MODIFIED) — Extend `make_id_token(...)` default behavior to accept a `groups` kwarg threaded into the claims dict (backwards compatible — default `groups=None` means the claim is omitted, matching today's behavior). The existing `claims_override` already handles ad-hoc cases; adding a first-class `groups=` kwarg makes the integration tests in #10 read cleanly.
12. **`services/bff/tests/models/entities/test_session.py`** (MODIFIED — if it exists; otherwise this is a NEW file) — Add a parametrized test asserting the `roles` column accepts `""` and `"reader"` and `"admin,reader"` and that NOT NULL is enforced at the SQLModel layer.

What this story **does NOT do** (out of Epic 7.1 scope — do not touch any of these here):

- **SPA changes** — the demo is exercisable from `curl` from the host (see AC6 below for the verification commands). A "🛡️ Admin: yes/no" badge in TopChrome is out of scope; if a follow-up wants to add it, the data is available via `GET /api/me/roles`.
- **Resource Server** — the RS keeps scope-based enforcement unchanged. Do not edit `services/resource-server/**`.
- **CSRF** — the new endpoints are GET-only (CSRF middleware exempts safe methods at `services/bff/src/bff/auth/csrf.py`). No CSRF cookie / header / Origin work required.
- **`/api/me`** existing endpoint — do NOT change the existing `GET /api/me` response shape. Add new endpoints; do not extend the existing payload to carry roles (a follow-up story can fold roles into `/api/me` if a SPA consumer needs it; this story keeps the demo cleanly separated).
- **Stories 7.2 + 7.3** — discovery bootstrap (P6) and structured auth-decision logs (P8) are separate stories in Epic 7. Do not anticipate their changes here. Logging in 7.1 stays plain `logger.info(...)` per existing BFF conventions; 7.3 will convert these to structured `extra={...}` payloads.
- **Existing `code_verifier` column on `auth_states`** — the post-PKCE-removal Pattern Amendments left it as nullable dead schema (architecture line 866). Do not touch it. This story's migration is `sessions`-only.
- **Tests' existing baseline shape** — the existing BFF test count post-PKCE-removal is the new baseline. Do not rewrite Story 1.5 tests for unrelated cleanup.

## Acceptance Criteria

> Source: existing AC scaffold in this file (pre-context-engine draft) + sprint-change-proposal-2026-05-21.md §4 Group I. Re-derived here with concrete file paths, exact line citations verified against the current code at HEAD `760cbb2`, and probe commands.

### AC1 — Realm carries a `groups` claim mapper + the two demo users are group members

**Given** the current `keycloak/realm-bmad-books.json` declares a `bmad-books-bff` client with an `aud-resource-server` mapper and a `sub` mapper (lines 88–115) and two pre-seeded users `testuser` (line 129) and `freshuser` (line 144),
**When** Story 7.1 closes,
**Then** the realm JSON has:
1. A new top-level `"groups"` array declaring two groups (`{"name": "reader", "path": "/reader"}` and `{"name": "admin", "path": "/admin"}`).
2. A new entry in the `bmad-books-bff` client's `protocolMappers` array of type `oidc-group-membership-mapper`:
   ```json
   {
     "name": "groups",
     "protocol": "openid-connect",
     "protocolMapper": "oidc-group-membership-mapper",
     "consentRequired": false,
     "config": {
       "full.path": "false",
       "id.token.claim": "true",
       "access.token.claim": "true",
       "userinfo.token.claim": "false",
       "claim.name": "groups",
       "jsonType.label": "String"
     }
   }
   ```
   `full.path: false` emits bare group names (e.g., `"reader"`) instead of paths (e.g., `"/reader"`) — the role mapper expects bare names.
3. `testuser` carries `"groups": ["reader"]` in the realm JSON's `users[]` entry (current line 129–141).
4. `freshuser` carries `"groups": ["reader", "admin"]` (current line 143–157).

> **Verification command** (post-up):
> ```bash
> docker compose up -d keycloak --wait
> # Log in as testuser via /auth/login → /auth/callback round-trip,
> # then decode the stored id_token and assert the groups claim is present.
> # The synthetic-IdP integration tests assert this at unit level; for a live
> # smoke, run `just e2e-up` after Story 7.1 and watch j1 still pass.
> ```
> Expected: `just e2e-up` exits 0 with 26/26 specs green — the groups claim is additive, not breaking.

> **Failure-prevention note (Keycloak group format):** Keycloak's `oidc-group-membership-mapper` emits a JSON array of strings into the claim. With `full.path: false` the array members are bare group names; with `full.path: true` they are slash-prefixed (`"/reader"`). Set `false` so the BFF mapper can do a simple `group_name in {"reader", "admin"}` comparison without slash-stripping.

> **Failure-prevention note (case sensitivity):** Keycloak group names are case-sensitive. The realm seeds lowercase `reader` and `admin`; the BFF's `Role.READER.value` and `Role.ADMIN.value` MUST also be lowercase `reader` / `admin` for the mapper to match. Do not capitalize.

### AC2 — BFF defines a `Role` enum and a pure claim→role mapper

**Given** the new module `services/bff/src/bff/auth/role_mapping.py` does not yet exist,
**When** Story 7.1 closes,
**Then** the module declares:
```python
"""Pure claim → in-app role mapper for the BFF (Story 7.1).

The BFF (not the AS) owns the mapping from raw OIDC `groups` claim values
to in-app `Role` enum members. This is the ACME-TS principle P4 boundary:
the IdP authenticates and asserts attributes; the application maps
attributes to roles and enforces them.

This module is pure (no DB, no network, no I/O). All call sites are in
`bff.api.auth` at the /auth/callback success path.
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
            # Unknown group name → ignore (per AC).
            continue
    return frozenset(out)
```

The function is **pure** — no DB, no network, no logging side effects, no global state. Reads from a `Mapping[str, Any]` (the verified id_token claims dict produced by `verify_id_token(...)` at `services/bff/src/bff/api/auth.py:246`). Returns a `frozenset[Role]` for immutability (so callers can pass it around without defensive-copying).

> **Failure-prevention note (StrEnum vs Enum):** Use `enum.StrEnum` (Python 3.11+). The codebase pins Python 3.14 via the archetype, so `StrEnum` is available. `Role("reader")` succeeds and returns `Role.READER`; the call inside the mapper depends on this round-trip.

> **Failure-prevention note (frozenset return):** Returning a `frozenset` (not `set`) signals immutability and prevents accidental mutation at the call site. The persisted serialization is `",".join(sorted(r.value for r in roles))` — `sorted()` accepts any iterable, so a frozenset is fine.

### AC3 — Session row carries the mapped roles + Alembic migration

**Given** `services/bff/src/bff/models/entities/session.py` at HEAD has no `roles` column (current line 20–40), and `services/bff/alembic/versions/` contains exactly `0001_init_init_sessions_and_auth_states.py` and `0002_add_books.py`,
**When** Story 7.1 closes,
**Then**:
1. `session.py` gains `roles: str = Field(default="", nullable=False)` as the last column before `created_at` / `updated_at`. Update the module docstring (current lines 1–13) to mention that the column persists the comma-separated sorted role list per Story 7.1.
2. A new file `services/bff/alembic/versions/0003_session_roles.py` exists with:
   ```python
   """add roles column to sessions

   Revision ID: 0003_session_roles
   Revises: 0002_add_books
   Create Date: 2026-05-21 ...
   """

   from collections.abc import Sequence

   import sqlalchemy as sa
   import sqlmodel
   from alembic import op

   revision: str = "0003_session_roles"
   down_revision: str | Sequence[str] | None = "0002_add_books"
   branch_labels: str | Sequence[str] | None = None
   depends_on: str | Sequence[str] | None = None


   def upgrade() -> None:
       op.add_column(
           "sessions",
           sa.Column(
               "roles",
               sqlmodel.sql.sqltypes.AutoString(),
               nullable=False,
               server_default="",
           ),
       )


   def downgrade() -> None:
       op.drop_column("sessions", "roles")
   ```
3. `session_service.create_session(...)` (current line 133) gains a `roles: frozenset[Role]` keyword argument. The implementation persists `",".join(sorted(r.value for r in roles))` (or `""` for the empty frozenset).
4. The existing call site at `services/bff/src/bff/api/auth.py:272–279` is updated to pass `roles=mapped_roles` where `mapped_roles = map_claims_to_roles(claims)`.

> **Failure-prevention note (NOT NULL + `server_default=""`):** The `server_default=""` clause is required because SQLite enforces NOT NULL at the column-add step for existing rows. Without it, the migration fails on a DB that already has session rows (the test_reset fixture seeds them). The SQLModel `Field(default="")` covers ORM-side inserts; `server_default=""` covers the migration itself.

> **Failure-prevention note (no separate `roles` table):** The story persists roles as a comma-separated string in a single column rather than a join table. Rationale: the demo's value is the architectural pattern, not query flexibility; the cardinality is low (2 possible roles, max ~2 chars per name); the read path is "load session row, parse string, check membership" which doesn't benefit from a JOIN. If a future story needs to query "all sessions with admin role", that story can normalize the schema.

> **Failure-prevention note (sorted serialization):** `",".join(sorted(r.value for r in roles))` is deterministic: `frozenset({Role.READER, Role.ADMIN})` → `"admin,reader"` regardless of insertion order. Tests assert the sorted form; the `/api/me/roles` endpoint also sorts its array output for the same reason.

### AC4 — One demo endpoint is role-gated + a roles-readout endpoint

**Given** `services/bff/src/bff/api/me.py` currently exposes only `GET /api/me` (line 51) and uses the session-cookie validation pattern at lines 56–80,
**When** Story 7.1 closes,
**Then** the same file exposes two additional endpoints sharing the existing validation helper:

1. **`GET /api/me/roles`** — Returns `{"roles": ["admin", "reader"]}` (alphabetically sorted) for a valid session. The roles array is parsed from `Session.roles` by `[r for r in row.roles.split(",") if r]` (split-and-filter handles the empty-string case). Returns 401 `session_expired` for missing/unknown/expired sessions (same lazy-delete path as `/api/me`).
2. **`GET /api/admin/ping`** — Returns 200 `{"ok": true}` IF the session's stored roles contain `"admin"`. Otherwise returns 403 with the `forbidden_scope` envelope:
   ```json
   {"errorCode": "forbidden_scope", "message": "Required role missing", "detail": null}
   ```
   Returns 401 `session_expired` for missing/unknown/expired sessions (the 401 takes priority over the 403 — an unauthenticated request never sees the role check).

The order of checks at `/api/admin/ping` is:
```
1. Session cookie present?           No → 401 session_expired
2. Session row exists in DB?         No → 401 session_expired
3. Session row not expired?          No → lazy-delete + 401 session_expired
4. Session row roles contains admin? No → 403 forbidden_scope
5. → 200 {"ok": true}
```

The implementation reuses the helpers in `services/bff/src/bff/api/me.py:36–48` (the `_session_expired_response()` factory and `_as_utc_aware(...)`). A new `_forbidden_scope_response()` factory mirrors the shape using the new `ErrorCode.FORBIDDEN_SCOPE` from AC8 / errors.py.

> **Verification command** (post-up):
> ```bash
> # After auth-login → callback round-trip via the synthetic IdP harness OR live Keycloak:
> COOKIE_JAR=/tmp/jar.txt
> # 1) testuser (reader only) → 403 on admin/ping
> curl -s -b $COOKIE_JAR -o - -w "%{http_code}\n" http://localhost:4000/api/admin/ping
> # Expected: HTTP 403, body {"errorCode":"forbidden_scope","message":"Required role missing","detail":null}
> # 2) testuser → 200 on /api/me/roles with ["reader"]
> curl -s -b $COOKIE_JAR -o - -w "%{http_code}\n" http://localhost:4000/api/me/roles
> # Expected: HTTP 200, body {"roles":["reader"]}
> # 3) freshuser (reader + admin) → 200 on admin/ping
> # (log out, log back in as freshuser, then re-curl)
> ```

> **Failure-prevention note (router mount):** The new endpoints are added to the existing `me` router at `services/bff/src/bff/api/me.py:27` (`router = APIRouter(tags=["Auth"])`). The router is already included by `services/bff/src/bff/main.py:59`. Do NOT create a new router or call `app.include_router(...)` again — the existing wiring handles all three endpoints. The endpoint paths (`/api/me`, `/api/me/roles`, `/api/admin/ping`) are different enough that no path conflicts arise.

> **Failure-prevention note (CSRF middleware):** The CSRF middleware at `services/bff/src/bff/auth/csrf.py` exempts safe methods (GET/HEAD/OPTIONS). Both new endpoints are GET, so the middleware passes them through without requiring a CSRF cookie or header.

> **Failure-prevention note (CORS):** CORS settings are managed by `services/bff/src/bff/main.py:40` reading `settings.cors_enabled`. The new endpoints are same-origin from the browser via the SPA edge proxy (Epic 6); no CORS configuration changes are needed.

### AC5 — Tests

**Given** the test files at `services/bff/tests/auth/` and `services/bff/tests/api/` follow the pytest+httpx+respx pattern established by Story 1.5,
**When** Story 7.1 closes,
**Then**:

1. **`services/bff/tests/auth/test_role_mapping.py`** (NEW) exhaustively parametrizes the cases listed in Deliverable 9 above. Coverage of `services/bff/src/bff/auth/role_mapping.py` is ≥90% line (per Story 5.1 per-file floor; realistically 100% since the module is ~20 lines).
2. **`services/bff/tests/api/test_admin_ping.py`** (NEW) covers `GET /api/admin/ping` and `GET /api/me/roles` per the test list in Deliverable 10 above. Uses the synthetic IdP harness to mint id_tokens with the `groups` claim. Coverage of the new endpoint code paths in `services/bff/src/bff/api/me.py` is ≥80% line.
3. **`services/bff/tests/services/test_session_service.py`** (MODIFIED) — Add a single test asserting `create_session(..., roles=frozenset({Role.READER, Role.ADMIN}))` persists `"admin,reader"` (sorted) into the new column. Add a second test asserting `create_session(..., roles=frozenset())` persists `""`.
4. **`services/bff/tests/api/test_auth.py`** (MODIFIED) — Extend the `_complete_login` helper (existing test fixture from Story 1.5) to optionally seed a `groups=["reader"]` claim in the synthetic-IdP-minted id_token. Add one positive-path test asserting the post-callback session row carries `roles="reader"` for a single-group user.
5. **Aggregate BFF coverage** — `cd services/bff && uv run pytest --cov` exits 0 with aggregate `≥90%` (the post-Epic-6 baseline of ~97% per Story 5.1 has room; adding ~60 LOC of source and ~200 LOC of tests should hold aggregate above 90%). Per-file floors per Story 5.1's documented framing: ≥70% on the BFF aggregate's lowest-coverage file.

> **Failure-prevention note (synthetic IdP `claims_override`):** The harness at `services/bff/tests/auth/synthetic_idp.py:114` already accepts `claims_override` to inject arbitrary claims. The cleanest pattern for AC5 is:
> ```python
> id_token = idp.make_id_token(sub="test-sub-001", nonce=nonce, claims_override={"groups": ["reader", "admin"]})
> ```
> The optional first-class `groups=` kwarg added in Deliverable 11 is a readability nicety; the tests would work without it via `claims_override` alone.

> **Failure-prevention note (StoreFront re-use):** The `conftest.py` BFF test fixtures (`db_session`, `app`, `client`) at `services/bff/tests/conftest.py` are the same fixtures Story 1.5 + 1.6 + 2.x + 3.x + 4.x all reused. Do not introduce a new fixture surface; piggyback on existing ones.

### AC6 — Live demo round-trip works through the running compose stack

**Given** the deliverables in AC1–AC5 have landed and `docker compose up -d --wait` brings up the baseline stack (Keycloak + BFF + RS + SPA edge),
**When** the dev (or a reviewer) runs the verification commands below,
**Then** all three round-trips behave as documented.

This AC is **dev-attestation**: the dev runs the commands locally, captures the output transcripts (HTTP codes + JSON bodies), and pastes them into the story's Dev Notes / Completion Notes. The probes are deliberately curl-only — no browser, no SPA UI work needed.

```bash
# Bring up the baseline stack
docker compose up -d --wait

# Probe 1: log in as testuser through the SPA edge (302 chain handled by curl -L + cookie jar)
COOKIE_JAR_TEST=/tmp/testuser_cookies.txt
rm -f $COOKIE_JAR_TEST
# Step the user through /auth/login → Keycloak login form → callback. This is
# a 4-hop redirect that curl can drive end-to-end with -L --cookie-jar.
# (See `docs/smoke-run.md` Mode-B HTTP-probe section for the full curl recipe;
# Story 7.1's dev attestation adapts the same approach for testuser AND freshuser.)

# Probe 2: testuser → /api/me/roles returns ["reader"]
curl -s -b $COOKIE_JAR_TEST -o - -w "\nHTTP %{http_code}\n" http://localhost:4000/api/me/roles
# Expected: {"roles":["reader"]}\nHTTP 200

# Probe 3: testuser → /api/admin/ping returns 403 forbidden_scope
curl -s -b $COOKIE_JAR_TEST -o - -w "\nHTTP %{http_code}\n" http://localhost:4000/api/admin/ping
# Expected: {"errorCode":"forbidden_scope","message":"Required role missing","detail":null}\nHTTP 403

# Probe 4: log out, log in as freshuser, repeat probes 2 + 3
COOKIE_JAR_FRESH=/tmp/freshuser_cookies.txt
# ... freshuser login round-trip ...
curl -s -b $COOKIE_JAR_FRESH -o - -w "\nHTTP %{http_code}\n" http://localhost:4000/api/me/roles
# Expected: {"roles":["admin","reader"]}\nHTTP 200
curl -s -b $COOKIE_JAR_FRESH -o - -w "\nHTTP %{http_code}\n" http://localhost:4000/api/admin/ping
# Expected: {"ok":true}\nHTTP 200

docker compose down
```

The dev pastes the literal stdout (HTTP codes + bodies) into the Completion Notes block at story close, the same way Story 5.4 / 6.4 captured Mode-B HTTP-probe transcripts.

> **Failure-prevention note (cookie jar isolation):** Use separate cookie jars per user (`$COOKIE_JAR_TEST`, `$COOKIE_JAR_FRESH`). Mixing them in a single jar leaks the testuser session cookie into the freshuser probes and the role check will silently use the wrong session row.

> **Failure-prevention note (J1 E2E spec still passes):** `just e2e-up` should still exit 0 with 26/26 specs green. The `groups` claim is additive; no Playwright spec asserts on the absence of group data, so adding it should not break any existing journey. If a spec does break, the regression is likely in `_complete_login`-equivalent helper code that's now seeing an unexpected claim shape.

### AC7 — No surface outside the Deliverables list is modified

**Given** the 12 deliverables in §Scope cover every file Story 7.1 touches,
**When** the dev runs `git diff --stat` at story close,
**Then** the diff includes ONLY:
- `keycloak/realm-bmad-books.json`
- `services/bff/src/bff/auth/role_mapping.py` (new)
- `services/bff/src/bff/models/entities/session.py`
- `services/bff/alembic/versions/0003_session_roles.py` (new)
- `services/bff/src/bff/services/session_service.py`
- `services/bff/src/bff/api/auth.py`
- `services/bff/src/bff/api/me.py`
- `services/bff/src/bff/core/errors.py`
- `services/bff/tests/auth/test_role_mapping.py` (new)
- `services/bff/tests/api/test_admin_ping.py` (new)
- `services/bff/tests/auth/synthetic_idp.py`
- `services/bff/tests/models/entities/test_session.py` (new or modified)
- `services/bff/tests/services/test_session_service.py`
- `services/bff/tests/api/test_auth.py`
- `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md` (this file — status / Dev Notes / Completion Notes)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (the status flips)
- Optional: `_bmad-output/implementation-artifacts/deferred-work.md` (only if the dev logs new defers — story explicitly does NOT require any)

No other file MUST appear in the diff. In particular: no `docs/` edits, no `README.md` edits, no `spa/**` edits, no `services/resource-server/**` edits, no `compose/**` edits, no `_bmad-output/planning-artifacts/**` edits (the planning artifacts already reflect Epic 7 from the 760cbb2 plan-for-epic-7 commit).

## Dependencies

- **Closes** principle gap **P4** (separation of authN/authZ) from `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §5 Epic 7 table.
- **Touches** (per AC7): Keycloak realm, BFF auth module (new), BFF session model + migration, BFF API surface (`me.py`), BFF errors enum, BFF tests.
- **Does NOT depend on** Stories 7.2 (OIDC discovery) or 7.3 (structured logs). The three Epic 7 stories are independent; the recommended sequence per sprint-change-proposal-2026-05-21.md §5 is **7.3 → 7.2 → 7.1** but the user can pick any order. This story is being picked first.
- **Does NOT touch** the Resource Server (which keeps scope-based enforcement as the parallel mechanism per §Scope).

## Developer Context

### Architecture Compliance

The story's pattern is **explicitly endorsed** by architecture §C5 (line 404) which declares `FORBIDDEN_SCOPE = "forbidden_scope" # HTTP 403` as a project-wide ErrorCode — the RS already implements it; this story adds the BFF half. The pattern is consistent with §C7 (distinct API Pydantic models over ORM serialization), §A3 / §A8 (cookie-session auth posture), §AR9 (server-side state in `sessions` row), and the Pattern Amendments entry at line 863 (PKCE removed — confidential client; the role-mapping work piles on the same confidential-client foundation).

The role enum and mapper sit in `services/bff/src/bff/auth/` alongside the existing `keycloak_cookie_session.py` and `csrf.py`. This is consistent with the directory's purpose: **authentication primitives owned by the BFF** (the cookie-session OIDC plugin, CSRF middleware, and now the claim→role mapper). The choice deliberately avoids `services/bff/src/bff/services/` (which holds I/O-coupled services) and `services/bff/src/bff/core/` (which holds framework wiring) — the role mapper is a pure function and belongs with the other auth primitives.

### Library / Framework Requirements

- **Python 3.14** (archetype-pinned). `enum.StrEnum` is available (PEP 663, Python 3.11+).
- **No new dependencies.** The role mapper uses only `collections.abc.Mapping`, `enum.StrEnum`, and `typing.Any` from the stdlib.
- **SQLModel 0.0.x** (whatever the archetype pins). The `Field(default="", nullable=False)` declaration is the same pattern the existing `csrf_secret` column at `services/bff/src/bff/models/entities/session.py:30` uses.
- **Alembic** (archetype-pinned). The migration file uses `sqlmodel.sql.sqltypes.AutoString()` to match the existing `0001_init` and `0002_add_books` migrations' column-type idiom.
- **FastAPI** decorators on the new endpoints follow the existing `@router.get("/api/me")` pattern at `services/bff/src/bff/api/me.py:51`.

### File Structure Requirements

**Source files** (mirror the existing structure):
- `services/bff/src/bff/auth/role_mapping.py` — pure mapper, no I/O.
- `services/bff/src/bff/models/entities/session.py` — single-column edit, docstring update.
- `services/bff/src/bff/services/session_service.py` — `create_session` signature + body edit.
- `services/bff/src/bff/api/auth.py` — callback-success path edit (lines 245–315).
- `services/bff/src/bff/api/me.py` — two new endpoints + new helper.
- `services/bff/src/bff/core/errors.py` — new `FORBIDDEN_SCOPE` enum member.
- `services/bff/alembic/versions/0003_session_roles.py` — new migration.

**Test files** (mirror source):
- `services/bff/tests/auth/test_role_mapping.py` — unit tests for the mapper.
- `services/bff/tests/api/test_admin_ping.py` — integration tests for the two new endpoints.
- `services/bff/tests/services/test_session_service.py` — add role-persistence tests.
- `services/bff/tests/auth/test_auth.py` — extend post-callback assertion.
- `services/bff/tests/auth/synthetic_idp.py` — add `groups=` first-class kwarg.
- `services/bff/tests/models/entities/test_session.py` — new or extended file.

**Realm file**:
- `keycloak/realm-bmad-books.json` — declared groups + group memberships + new protocolMapper.

### Testing Requirements

Per Story 5.1 (coverage audit) the BFF aggregate floor is ≥90% line + per-file ≥70%. The story's net source addition is small (~60 LOC across the new mapper, two endpoints, one helper, and the migration) so the aggregate impact is negligible. Run:

```bash
cd services/bff
uv run pytest --cov=bff --cov-report=term-missing --cov-fail-under=90
```

Per-file targets:
- `bff/auth/role_mapping.py` — 100% (10–15 LOC; exhaustive parametrization)
- `bff/api/me.py` — ≥85% (the new helper + two new endpoint bodies)
- `bff/services/session_service.py` — ≥90% (existing baseline, plus the new `roles=` kwarg path)
- `bff/core/errors.py` — coverage from existing `test_errors.py` if it exists, otherwise covered transitively by the integration tests

### Previous Story Intelligence (Epic 1 → Epic 6 close)

- **Story 1.5 baseline (Authorization Code + cookie session):** `services/bff/src/bff/auth/keycloak_cookie_session.py` is the OIDC plugin. `verify_id_token(...)` returns the decoded claims dict, which is exactly the input shape `map_claims_to_roles(...)` expects. The story does NOT add a new id_token verification call — it consumes the existing one.
- **Story 1.5 amendment 2026-05-21 (PKCE removed):** The Pattern Amendments entry at architecture.md:863 documents the post-PKCE state. The new `groups` claim flows through the same `id_token` channel — no flow shape change.
- **Story 1.6 (CSRF):** GET endpoints are exempt from CSRF middleware. Both new endpoints are GET; no CSRF work needed.
- **Story 1.7 (logout):** The logout endpoint at `services/bff/src/bff/api/auth.py:382` deletes the local `sessions` row including the new `roles` column. No logout-side edits needed.
- **Story 3.5 (resource_server_client refresh-replay):** The BFF's RS client at `services/bff/src/bff/services/resource_server_client.py` doesn't read `Session.roles` — refresh-replay only needs the access/refresh tokens. No edits to the RS client needed.
- **Story 5.2 (security review document):** §5 (scope enforcement) covers the RS side; Story 7.1 adds the BFF role side. Story 7.1 does NOT edit `docs/security-review.md` — a future story (or Story 7.3's structured logs work) can add a §5b "Role enforcement (BFF)" subsection if desired. Out of 7.1 scope.
- **Story 6.4 close (Epic 6):** The SPA SSR edge at `:4000` is the browser-facing origin. The BFF has no host-published port. All curl probes in AC6 go through `localhost:4000` (the SPA edge), which proxies `/api/admin/ping` and `/api/me/roles` to the BFF on the compose network. Same-origin pattern preserved.

### Git Intelligence Summary

Most-recent commit `760cbb2 plan for epic 7` added the Epic 7 sprint-change-proposal and the three Epic 7 story stubs (7-1, 7-2, 7-3 in `_bmad-output/implementation-artifacts/`). The Story 1.5 amendments + the PKCE-removal code edits all landed in the same commit. The BFF source tree is at the post-PKCE-removal state: `pkce.py` is deleted; `keycloak_cookie_session.py` uses `client_secret_basic`; `auth_states` still has the `code_verifier` column as nullable dead schema.

Prior commits relevant to this story's surface:
- `d26dd7c chore: stop tracking _bmad/ tooling directory` — no impact on BFF.
- `7b2eb9c implement epic 6` — closed Epic 6 (SPA SSR edge). The browser-facing origin moved BFF→SPA-edge; AC6 probes use `:4000` accordingly.
- `ed34ac7 fix(d140-d141): make bare docker compose up work for a fresh clone` — `docker compose up` activates the baseline stack with no `--profile` flag. Use bare `docker compose up -d --wait` in AC6 probes.

### Pattern Amendments / Architecture Touch Points

This story does NOT amend any architectural pattern. It implements one already documented in §C5 (the `FORBIDDEN_SCOPE` ErrorCode) and adds a new claim→role mapping primitive that fits the existing §A3 cookie-session foundation. No `Pattern Amendments` entry is required.

## Notes

- This is a **demo / reference-pattern** story. The POC's single-role product design (PRD §5) doesn't *require* roles. Story value is **architectural illustration** of the ACME pattern, not a product feature.
- No SPA changes required for AC1–AC7; the demo can be exercised with `curl` from the host. A small follow-up could add a `🛡️ Admin: yes/no` line to TopChrome via a new `RolesService` consuming `GET /api/me/roles` — **out of scope** for Story 7.1; capture as a deferred follow-up at code-review time if the dev wants to track it.
- The story is **small in code surface but careful in tests**. The hardest part is the realm-JSON edit (Keycloak group-mapper config). The next hardest is making sure the `0003_session_roles` migration runs cleanly against an existing-rows DB (the `server_default=""` is load-bearing — without it, the migration fails on a DB that has any pre-existing session row).
- **Recommended dev sequence:**
  1. Add `FORBIDDEN_SCOPE` to `core/errors.py` (smallest edit, unblocks everything).
  2. Write `auth/role_mapping.py` + its unit tests (pure module, fast TDD loop).
  3. Add the `roles` column + migration + update `session_service.create_session(...)` + update `api/auth.py` callback path.
  4. Add the two new endpoints in `api/me.py` + integration tests.
  5. Edit the Keycloak realm JSON + run a live `docker compose up` round-trip to verify the `groups` claim flows through.
  6. Capture the AC6 probe transcripts and paste into Completion Notes.

## Dev Notes

**Implementation order followed the recommended dev sequence** from §Notes:
1. `FORBIDDEN_SCOPE` ErrorCode added (`core/errors.py`).
2. `auth/role_mapping.py` written + 27 unit tests parametrized → all green.
3. `sessions.roles` column added; `0003_session_roles` migration; `session_service.create_session(...)` gained `roles=` kwarg; `api/auth.py` callback wires `map_claims_to_roles(claims)` into `create_session(..., roles=...)`.
4. `api/me.py` gained `GET /api/me/roles` + `GET /api/admin/ping` + shared `_load_active_session(...)` helper; 24 integration tests in `tests/api/test_admin_ping.py` → all green.
5. Keycloak realm JSON gained top-level `groups[]` array, `testuser` → `/reader`, `freshuser` → `/reader,/admin`, and the `oidc-group-membership-mapper` protocolMapper with `full.path=false`.
6. Live AC6 round-trip captured below.

**Anomaly A1 (pre-existing stale tests fixed)** — `tests/services/test_session_service.py` had three call sites (lines 92, 119, 133 at HEAD `760cbb2`) using the pre-PKCE-removal tuple-unpack `row, _ = await service.create_auth_state(...)`. The PKCE-removal Group F.6 (sprint-change-proposal-2026-05-21.md) claimed those were converted to single-value unpack but missed these three. Fixed in this story because the test suite cannot run green otherwise and AC5 demands `pytest --cov` exits 0. The fix is structural-trivial (drop `, _`); no test assertion changed. Mirrors Story 6.4's Anomaly A1 precedent (out-of-scope test edits required to keep the suite green after a prior change).

**Scope decision: `tests/models/entities/test_session.py` not added.** Deliverable 12 framed this as "new or modified file". The new `roles` column's behavior is fully covered through three paths:
- The service layer in `tests/services/test_session_service.py` (`test_create_session_persists_row` asserts default `""`; `test_create_session_persists_roles_sorted` asserts sorted serialization; `test_create_session_persists_empty_roles` asserts empty + single-role paths).
- The HTTP layer in `tests/api/test_admin_ping.py` (12 cases including parametrized `test_admin_ping_membership_check_is_string_based` over `""`, `"reader"`, `"admin"`, `"admin,reader"`, `"reader,admin"`).
- The full-flow path in `tests/api/test_auth.py` (`test_auth_callback_persists_mapped_roles_from_groups_claim` + 2 more) asserting the column populates correctly from a live id_token.
A standalone entity-level test would only re-exercise SQLModel's NOT NULL behavior, which is library code. Recorded here so a reviewer doesn't need to dig for the missing file.

**Migration filename:** The story's AC3 noted the existing draft mis-named the new migration `0002_session_roles`. Landed as `0003_session_roles.py` (`down_revision = "0002_add_books"`) — correct slot at HEAD `760cbb2`.

**Aggregate coverage achieved:** 97.58% (562 tests). `role_mapping.py` 100%, `errors.py` 100%, `models/entities/session.py` 100%, `api/me.py` 100%. Lowest per-file: `core/database.py` 84% (above 70% Story-5.1 floor; pre-existing baseline).

## Completion Notes

**AC6 live HTTP-probe transcript (Mode-B dev attestation, baseline `760cbb2`):**

Bring-up: `docker compose down -v` → `cp .env.example .env` → `docker compose up -d --wait`. All four services healthy: keycloak / bff / resource-server / spa.

**testuser (group=reader)**

```
=== /api/me/roles (testuser) ===
{"roles":["reader"]}
HTTP 200

=== /api/admin/ping (testuser) ===
{"errorCode":"forbidden_scope","message":"Required role missing","detail":null}
HTTP 403

=== /api/me (testuser) — baseline ===
{"sub":"7122ac0e-249b-4f2e-ba0d-ad0ea179161d","preferred_username":"testuser"}
HTTP 200
```

**freshuser (groups=reader,admin)**

```
=== /api/me/roles (freshuser) ===
{"roles":["admin","reader"]}
HTTP 200

=== /api/admin/ping (freshuser) ===
{"ok":true}
HTTP 200

=== /api/me (freshuser) — baseline ===
{"sub":"dd680bed-8c41-4be9-903c-00fd73665087","preferred_username":"freshuser"}
HTTP 200
```

Login round-trip was driven via curl + cookie jars (`/tmp/login_via_kc.sh` shell helper drives `/auth/login → KC login form → POST credentials → /auth/callback` end-to-end). The wire-shape of all six probes matches AC4 / AC6 exactly: 200 on `/api/me/roles` returns the alphabetically sorted role array; 403 on `/api/admin/ping` returns the canonical `forbidden_scope` envelope; 200 on `/api/admin/ping` returns `{"ok":true}`; 200 on `/api/me` continues to return the existing `{sub, preferred_username}` shape unchanged.

Final teardown: `docker compose down` (no `-v` — volumes preserved for an operator's follow-up walk-through).

**Verdict: PASS** — all 7 ACs satisfied via test suite + live AC6 transcript. AC7 (diff scope) verified: 14 files modified, all in the AC7 allowlist (one allowlist item `tests/models/entities/test_session.py` was deliberately not added — see Dev Notes scope decision).

**No new defers logged.** Anomaly A1 (pre-existing tuple-unpacks) is documented in Dev Notes; not registered in deferred-work.md because the fix landed in this story.

## Change Log

| Version | Date       | Description                                                                                                     |
|---------|------------|-----------------------------------------------------------------------------------------------------------------|
| v1.0    | 2026-05-21 | Story contexted from sprint-change-proposal-2026-05-21.md §4 Group I; 7 ACs + 12 deliverables enumerated.        |
| v1.1    | 2026-05-21 | Dev implementation: role_mapping module + roles column + 0003 migration + 2 new endpoints + realm group-mapper + 30 new tests (562/562 green, 97.58% aggregate cov). Live AC6 transcript captured for testuser + freshuser. Anomaly A1 pre-existing PKCE-cleanup tuple-unpacks fixed. Status → review. |

## File List

**New files**
- `services/bff/src/bff/auth/role_mapping.py` — `Role(StrEnum)` + `map_claims_to_roles(...)` + `serialize_roles(...)` + `deserialize_roles(...)`.
- `services/bff/alembic/versions/0003_session_roles.py` — adds `sessions.roles` NOT NULL column with `server_default=""`.
- `services/bff/tests/auth/test_role_mapping.py` — 27 unit tests for the pure mapper + serialization round-trips.
- `services/bff/tests/api/test_admin_ping.py` — 14 integration tests for `/api/me/roles` + `/api/admin/ping` (12 distinct scenarios + 5-row parametrize).

**Modified files**
- `keycloak/realm-bmad-books.json` — top-level `groups[]` + group memberships on `testuser` (`/reader`) and `freshuser` (`/reader,/admin`) + new `oidc-group-membership-mapper` on the `bmad-books-bff` client.
- `services/bff/src/bff/models/entities/session.py` — `roles: str = Field(default="", nullable=False)` column + docstring update.
- `services/bff/src/bff/services/session_service.py` — `create_session(...)` gained `roles: frozenset[Role] = frozenset()` keyword argument; imports `Role` + `serialize_roles`.
- `services/bff/src/bff/api/auth.py` — callback success path calls `map_claims_to_roles(claims)` + threads it through `create_session(...)`; INFO log line gains `roles=` field; module docstring updated.
- `services/bff/src/bff/api/me.py` — two new endpoints (`/api/me/roles`, `/api/admin/ping`); new `_load_active_session(...)` helper extracted; new `_forbidden_scope_response()` factory; `/api/me` refactored to use the shared helper; module docstring updated.
- `services/bff/src/bff/core/errors.py` — new `FORBIDDEN_SCOPE` enum member (architecture §C5).
- `services/bff/tests/auth/synthetic_idp.py` — `make_id_token(...)` gained first-class `groups: list[str] | None = None` keyword.
- `services/bff/tests/services/test_session_service.py` — 2 new tests (`test_create_session_persists_roles_sorted`, `test_create_session_persists_empty_roles`); existing `test_create_session_persists_row` extended with `assert row.roles == ""` line; 3 pre-existing stale tuple-unpacks fixed (Anomaly A1).
- `services/bff/tests/api/test_auth.py` — `_complete_login(...)` helper gained `groups=` kwarg; 3 new tests asserting the callback persists the mapped role set on `sessions.roles`.
- `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md` — Status → review; Dev Notes + Completion Notes + Change Log + File List populated.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `7-1-bff-claim-to-role-mapping-demo: in-progress → review`; `last_updated` field appended.

### Review Findings

Three-layer adversarial review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) ran in parallel against the Story 7.1 working-tree diff. 24 raw findings triaged → 2 patches + 5 defers + 17 dismissed.

**Patches:**
- [x] [Review][Patch] P1: Module docstring false claim about call sites — `role_mapping.py` states "All call sites are in `bff.api.auth` at the /auth/callback success path" but `bff.api.me` (imports `Role`, `deserialize_roles`) and `bff.services.session_service` (imports `Role`, `serialize_roles`) are additional consumers [services/bff/src/bff/auth/role_mapping.py:docstring] — **patched**: docstring updated to enumerate all three consumers
- [x] [Review][Patch] P2: `server_default=""` bare string generates empty SQL expression — should be `sa.text("''")`; the bare `""` becomes `DEFAULT ` (no value) in the DDL and would fail on a DB with pre-existing session rows; only undetected because AC6 used `docker compose down -v` (fresh DB) [services/bff/alembic/versions/0003_session_roles.py:upgrade()] — **patched**: `server_default=""` → `server_default=sa.text("''")`; migration docstring updated to explain the requirement

**Defers:**
- [x] [Review][Defer] D170: No length cap on `sessions.roles` column — `AutoString()` → TEXT (SQLite) / VARCHAR (Postgres) unbounded; content is bounded by the 2-member `Role` enum today but no DB-level guard exists; consistent with other token columns but roles are well-known values with a natural max length [services/bff/alembic/versions/0003_session_roles.py] — deferred
- [x] [Review][Defer] D171: Session roles frozen at login time — `sessions.roles` is populated once at `/auth/callback` and never refreshed; revoking a Keycloak group membership is invisible to the BFF until the session row expires; not documented as an accepted risk [services/bff/src/bff/api/me.py] — deferred
- [x] [Review][Defer] D172: GET /api/admin/ping is a role-probe side-channel — HTTP 200 vs 403 distinguishes admin from non-admin for any authenticated GET request; `SameSite=Lax` cookies are sent on top-level GET navigations; consistent with `/api/me` pattern but worth noting for a real RBAC deployment [services/bff/src/bff/api/me.py:admin_ping] — deferred
- [x] [Review][Defer] D173: `Session.roles` missing `repr=False` — inconsistent with `access_token`, `refresh_token`, `id_token`, `csrf_secret` pattern; role names appear in debug `__repr__` output; roles are not secret but the inconsistency is visible [services/bff/src/bff/models/entities/session.py] — deferred
- [x] [Review][Defer] D174: `map_claims_to_roles` no size cap on groups list — a crafted id_token carrying thousands of unknown group names causes thousands of `ValueError` instances to be constructed and caught in the mapper loop; theoretical DoS amplifier at `/auth/callback`; in practice bounded by IdP token size [services/bff/src/bff/auth/role_mapping.py:map_claims_to_roles] — deferred
