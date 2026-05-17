---
status: ready-for-dev
story_key: 4-1-rs-post-v1-estimate-endpoint-estimate-service-format-duration-helper
epic: 4
prerequisites: 3.1 (done — RS scaffold, `/health`, RS in compose default/dev/e2e, `core/errors.py` + `core/exceptions.py`, fail-fast OIDC config, Alembic env); 3.2 (done — `oidc_bearer` plugin, `get_authenticated_principal`, `require_scope`, `Principal.scopes`, `ErrorCode.SESSION_EXPIRED` + `FORBIDDEN_SCOPE`, synthetic-IdP harness in `tests/auth/synthetic_idp.py`); 3.3 (done — `ReadingSpeed` entity at `models/entities/reading_speed.py`, `reading_speed_service.get_for_user` raises `ReadingSpeedUnsetError`, `ErrorCode.READING_SPEED_UNSET` + `INVALID_INPUT`, `api/schemas/reading_speed.py` DTO convention, `validation_exception_handler` emits `invalid_input` + drops `input`); 3.4 (done — RS `/v1/test/reset` truncates `reading_speeds`, e2e overlay sets `AUTH_TYPE=oidc_bearer`); 3.5 (done — BFF `ResourceServerClient` pattern; Epic 4 Story 4.2 will consume this story's endpoint)
created: 2026-05-17
baseline_commit: fda53fc
---

# Story 4.1: RS — `POST /v1/estimate` endpoint + `estimate_service` + `format_duration` helper

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer enabling the marquee architectural interaction (J3),
I want the RS to expose `POST /v1/estimate` that computes a user's reading time from their stored reading speed and the request's book pages, scope-gated by `reading-speed:read`, returning a formatted duration string the SPA can render directly,
so that the BFF can broker estimates without the SPA ever needing to format durations or know about the cross-service split.

## Scope (read this first)

This story is **RS-only** — the BFF `POST /v1/books/{id}/estimate` proxy + `ResourceServerClient.compute_estimate` is Story 4.2; the SPA `EstimateCell` real component is Story 4.3; the J3/J6 E2E specs are Story 4.4.

Concretely, this story delivers:

1. `src/resource_server/services/duration.py` (NEW) — `format_duration(minutes: int) -> str` per UX-DR18; boundary outputs pinned in tests.
2. `src/resource_server/services/estimate_service.py` (NEW) — `compute_for_user(session, sub, pages)` looks up the caller's `reading_speeds` row (reuses `reading_speed_service.get_for_user`), computes `minutes` deterministically, returns the `(minutes, formatted)` pair.
3. `src/resource_server/api/schemas/estimate.py` (NEW) — `EstimateIn` (`pages: int`, `ge=1`, `extra="forbid"`) and `EstimateOut` (`minutes: int`, `formatted: str`).
4. `src/resource_server/api/estimate.py` (NEW) — `APIRouter` exposing `POST /v1/estimate` gated by `require_scope("reading-speed:read")`.
5. `src/resource_server/api/v1/__init__.py` — register the new router on the existing `/v1` wrapper alongside `reading_speed_router`.
6. `tests/services/test_duration.py` (NEW) — boundary table from AC2.
7. `tests/services/test_estimate_service.py` (NEW) — service-level happy/412/cross-user.
8. `tests/api/test_estimate.py` (NEW) — request-layer happy + every named-error-code path.

**Out of scope for 4.1:** any BFF code (Story 4.2), any SPA code (Story 4.3), any compose / e2e / Playwright change (Stories 4.4 / 3.6 already shipped the harness), the test-reset extension (3.4 already truncates `reading_speeds` — no estimate-specific state to truncate; `pages` lives in BFF's `books` table, not the RS).

## Acceptance Criteria

The epic's BDD acceptance criteria are reproduced verbatim from `epics.md` lines 1528–1577 below; AC numbers are added for traceability into Tasks and Tests.

### AC1 — Router + service module + schema files exist with the right shapes

**Given** `src/resource_server/api/estimate.py` registers an `APIRouter` (with `tags=["estimate"]`, no prefix here — the `/v1` prefix lives in `api/v1/__init__.py` per Story 3.3's convention),
**And** `src/resource_server/services/estimate_service.py` exposes `async def compute_for_user(session: AsyncSession, sub: str, pages: int) -> EstimateOut` (returning the **DTO**, not a domain object — the router becomes a thin pass-through; this mirrors Story 3.3's `reading_speed_service` returning the entity and the router constructing the DTO, but here the formatted string is service-level concern, not router-level, so the service returns the DTO directly),
**And** `src/resource_server/api/schemas/estimate.py` exports:

- `EstimateIn(BaseModel)` with `pages: int = Field(ge=1)` and `model_config = ConfigDict(extra="forbid")` (mirrors `ReadingSpeedUpsert` from Story 3.3 — `extra="forbid"` rejects body-level `sub` injection attempts at the boundary),
- `EstimateOut(BaseModel)` with `minutes: int` and `formatted: str`.

**Then** all four files are present, importable, and exposed via:

- `services/__init__.py` — left as-is (Story 3.3 verified `services/__init__.py` is empty; modules are imported directly, e.g., `from resource_server.services import estimate_service`).
- `api/schemas/__init__.py` — left as-is (docstring only; modules imported directly).
- `api/v1/__init__.py` — adds `from resource_server.api.estimate import router as estimate_router` and `router.include_router(estimate_router)` alongside the existing `reading_speed_router` registration.

### AC2 — `format_duration(minutes: int) -> str` helper with pinned boundary outputs (UX-DR18)

**Given** a duration-formatting helper at `src/resource_server/services/duration.py` exposes `format_duration(minutes: int) -> str`,
**When** the helper is tested with boundary inputs,
**Then** the following outputs hold (with `≈` followed by a single ASCII space as the leading characters per UX-DR18 examples — `ux-design-specification.md:232,250,478` write the example as `"≈ 4 h 20 m"`, `"≈ 12 m"`, `"≈ 1 d 2 h"`):

| input minutes | expected output |
|---|---|
| `1` | `"≈ 1 m"` |
| `12` | `"≈ 12 m"` |
| `60` | `"≈ 1 h"` |
| `61` | `"≈ 1 h 1 m"` |
| `260` | `"≈ 4 h 20 m"` |
| `1440` | `"≈ 1 d"` |
| `1441` | `"≈ 1 d 1 m"` |
| `1500` | `"≈ 1 d 1 h"` |
| `2780` | `"≈ 1 d 22 h 20 m"` |

**Pinned rule:** for inputs `≥ 1440` (one day), emit days, hours, AND minutes when any are non-zero (i.e., the **first row above** for `2780` — `"≈ 1 d 22 h 20 m"`). Do NOT omit minutes when days are present. The epic AC explicitly offers the implementer a choice between the two `2780` outputs; this story **pins the include-minutes rule** so the test table and the J3 E2E assertions (Story 4.4) line up against a single deterministic output. If the dev finds a strong reason to flip the rule, surface it in Completion Notes and update the test verbatim — do not silently change the rule.

**Edge cases the helper must handle:**

- `format_duration(0)` is **not** a happy-path input (the endpoint's `Field(ge=1)` + the upstream `pages_per_hour ≥ 1` + the `ceil` rounding rule below guarantee `minutes ≥ 1` for every legal request). Defensive return: `"≈ 0 m"` so a future caller (e.g., a coverage gap-fill in Story 5.1) doesn't trigger an unhandled-branch crash. Pin this in the test table as a single line so the behavior is intentional.
- The helper must NOT accept negative input — negatives indicate a bug upstream. Raise `ValueError("format_duration requires a non-negative integer")` for `minutes < 0`. Pin this in tests.
- `int | float` type narrowing: take `int` only. If the upstream rounding rule (AC3) changes to produce a `float`, that's a contract break, not something the formatter should paper over.

**Format-string convention (project-internal):** use f-string parts joined with single spaces. The `≈` character is U+2248 (ALMOST EQUAL TO) — copy from the AC table above, not from the UX spec to avoid look-alike substitution. Pin via a module-level constant `_PREFIX = "≈"` so a future reviewer can grep for the symbol cleanly.

### AC3 — `estimate_service.compute_for_user(session, sub, pages)` computes minutes deterministically

**Given** a valid JWT with scope `reading-speed:read` and `sub = S`,
**And** a `reading_speeds` row exists for `sub = S` with `pages_per_hour = p`,
**When** `POST /v1/estimate` is called with body `{"pages": n}`,
**Then** `estimate_service.compute_for_user(session, S, n)`:

1. Calls `reading_speed_service.get_for_user(session, sub)` (reuse — do not duplicate the SELECT logic; the existing service already raises `ReadingSpeedUnsetError` when the row is absent, which maps to 412 via the existing `app_exception_handler`).
2. Computes `minutes = math.ceil(n * 60 / p)` (**pinned rounding rule** — ceiling so a partial minute always rounds up; this is the AC's example formula and aligns with the formatted-output contract that "the SPA renders the formatted string verbatim").
3. Returns `EstimateOut(minutes=minutes, formatted=format_duration(minutes))`.

**Determinism:** for fixed `(p, n)`, `minutes` is identical across runs and environments (no `time.time()`, no `random`, no float-rounding non-determinism — `math.ceil` on the rational `n * 60 / p` is stable). Python's `math.ceil` on a float is the float-domain ceiling; for the (n, p) ranges this story serves (`n ≤ ~10**6 pages`, `p ∈ [1, 10000]` per architecture's pragmatic ranges — see Dev Notes "Input bounds"), the float precision is more than sufficient. Document this in the service module docstring with one line referencing `python-docs/math.html#math.ceil`.

**No identity in the body or path:** the service signature accepts `sub: str`, and the router passes `principal.subject`. The router never accepts a body or path identifier for the user (per architecture line 388: "All RS endpoints read user identity from the JWT `sub` claim — no path or body identifier accepted for user"). The body's `EstimateIn` schema has **only** `pages`, and `extra="forbid"` rejects body-level `sub` injection attempts at the boundary as 422 `invalid_input` rather than silently dropping them.

**Service returns DTO, not entity** — deliberately different from `reading_speed_service.get_for_user`'s return shape (entity), because the formatted string is a presentation concern that should live alongside the `(minutes, formatted)` pair the router emits verbatim. The router becomes:

```python
@router.post("/estimate", response_model=EstimateOut)
async def post_estimate(
    payload: EstimateIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))],
) -> EstimateOut:
    return await estimate_service.compute_for_user(session, principal.subject, payload.pages)
```

### AC4 — Happy path: 200 with `{"minutes", "formatted"}`

**Given** a valid `reading-speed:read` JWT for `sub = S` and a `reading_speeds` row with `pages_per_hour = 30`,
**When** `POST /v1/estimate` is called with body `{"pages": 600}` (Story 4.4's J3 happy-path input),
**Then** the RS responds 200 with body `{"minutes": 1200, "formatted": "≈ 20 h"}`.

Verification: `math.ceil(600 * 60 / 30) = math.ceil(1200.0) = 1200`. `format_duration(1200)` → `"≈ 20 h"` (no minutes component because `1200 % 60 == 0`).

### AC5 — 403 `forbidden_scope` when only `reading-speed:write` is present

**When** `POST /v1/estimate` is called with a JWT carrying only `reading-speed:write` (no read scope),
**Then** the RS responds 403 with body `{"errorCode": "forbidden_scope", "message": "Required scope is missing", "detail": null}`.

This is automatic via `require_scope("reading-speed:read")` — Story 3.2's plumbing. No new code; test the wired-up behavior.

### AC6 — 412 `reading_speed_unset` on missing row (J3 freshuser precondition)

**When** `POST /v1/estimate` is called for a JWT whose `sub` has no `reading_speeds` row (the J3 precondition path Story 4.4 exercises via `freshuser`),
**Then** the RS responds 412 with body `{"errorCode": "reading_speed_unset", "message": "Reading speed not set for this user", "detail": null}`.

This is automatic via `reading_speed_service.get_for_user` raising `ReadingSpeedUnsetError` (Story 3.3) + the existing `app_exception_handler` (Story 3.1). No new code; test the wired-up behavior.

### AC7 — 422 `invalid_input` on non-positive or non-integer `pages`

**When** `POST /v1/estimate` is called with body `{"pages": 0}` or any non-positive integer (`-1`, `-100`),
**Then** the RS responds 422 with `errorCode: "invalid_input"`.

**When** `POST /v1/estimate` is called with body missing `pages`, or with `pages` as a non-integer (`"six hundred"`, fractional float `1.5`),
**Then** the RS responds 422 `invalid_input`.

**When** the body is **not a JSON object** (e.g., `[]`, `"hello"`, raw integer `42`),
**Then** the RS responds 422 `invalid_input` (Pydantic's model validation surfaces this; pin a test so a future refactor that swaps `EstimateIn` for a `RootModel` is caught).

All 422 responses MUST drop the user-supplied `input` field from each detail entry (verify by asserting `"input" not in entry` for each entry in `body["detail"]`). This is automatic via Story 3.3's `validation_exception_handler` sanitization — pin it in tests to catch regression.

### AC8 — 401 `session_expired` on missing / malformed / wrong-aud / wrong-iss / expired JWT

**When** `POST /v1/estimate` is called without a valid `Authorization` header (header missing entirely, malformed, expired, wrong audience, wrong issuer, forged signature),
**Then** the RS responds 401 with `errorCode: "session_expired"` (Story 3.2's `oidc_bearer.get_authenticated_principal` raises `AppException(ErrorCode.SESSION_EXPIRED)` for all of these — verified at `services/resource-server/src/resource_server/auth/oidc_bearer.py:88-93`).

Test cases:

- No `Authorization` header.
- `Authorization: Basic ...` (wrong scheme).
- Bearer with empty / whitespace-only token.
- Bearer with a JWT signed by a different keypair (use `SyntheticRsIdp` with a fresh keypair).
- Bearer with `exp_offset_seconds=-1` (expired).
- Bearer with `aud="wrong-audience"`.
- Bearer with `iss="http://wrong-issuer/..."`.

(Not all variants need an exhaustive test; cover at least: no-header, wrong-scheme, expired, wrong-audience. The full negative-scope is already exercised in `tests/auth/test_oidc_bearer.py` — Story 4.1 trusts that and tests the wired-up `/v1/estimate` only on the no-header + expired paths.)

### AC9 — Sub-injection via body is ignored

**Given** identity propagation (NFR6),
**When** `POST /v1/estimate` is called with a body containing additional fields like `{"pages": 600, "sub": "<spoof>"}`,
**Then** the request is rejected as 422 `invalid_input` (`EstimateIn` carries `extra="forbid"`, mirroring `ReadingSpeedUpsert` from Story 3.3 CR1). The Pydantic error entry has `type == "extra_forbidden"`.

**This is the harder-to-test invariant:** if a future refactor relaxes `extra="forbid"` to `extra="ignore"`, the request would 200 successfully (with `pages=600` and `sub` silently dropped). The test MUST assert the **422 + extra_forbidden type**, NOT just "the resulting estimate uses the JWT sub" — the latter passes under both configs.

**Cross-user invariant:** add a second test where User A's JWT (`sub=user-a`, `pages_per_hour=30` row exists) posts `{"pages": 600, "sub": "user-b"}`. The 422 fires; if a future config change weakens `extra="forbid"`, the assertion to extend at that point is "the estimate is computed from `user-a`'s row, not `user-b`'s" — but for v1, 422 is the contract.

### AC10 — Cross-user isolation

**Given** two users with subs `S1` and `S2` and distinct `reading_speeds` rows (`p1 = 30`, `p2 = 60`),
**When** each issues `POST /v1/estimate` with `{"pages": 600}` using their own JWT,
**Then** the responses are `{"minutes": 1200, "formatted": "≈ 20 h"}` and `{"minutes": 600, "formatted": "≈ 10 h"}` respectively — no cross-contamination, no shared session state.

### AC11 — Speed-changes-estimate-changes (J4↔J3 coupling)

**Given** a single user with a `reading_speeds` row,
**When** `POST /v1/estimate {"pages": 600}` is called twice with the same JWT — once with `pages_per_hour=30` (row pre-seeded), then again after PUT-ing `pages_per_hour=60`,
**Then** the first response is `{"minutes": 1200, "formatted": "≈ 20 h"}` and the second is `{"minutes": 600, "formatted": "≈ 10 h"}`. The second's `minutes` is strictly less than the first's.

This pins Story 4.4's J3 "speed change yields different estimate" assertion at the RS layer — if a future refactor introduces a per-process estimate cache keyed only by `(sub, pages)`, this test catches the resulting stale `minutes`.

### AC12 — Test coverage: every named code path + boundary table + ≥90% on the three new files

**Given** the RS test suite,
**When** the following commands run from `services/resource-server/`:

```sh
uv run pytest tests/api/test_estimate.py \
              tests/services/test_estimate_service.py \
              tests/services/test_duration.py
```

**Then** they exit 0 with tests covering:

- **`tests/services/test_duration.py`** — every row from AC2's boundary table (parametrize cleanly), the `0` defensive return, the `< 0` ValueError, and a no-input-mutation property test (`assert format_duration(60) == "≈ 1 h"` called twice yields identical strings — pins purity).
- **`tests/services/test_estimate_service.py`** — happy path (seed row via `upsert`, call `compute_for_user`, assert `minutes` + `formatted`), missing row raises `ReadingSpeedUnsetError`, cross-user isolation, math invariants (ceiling: `pages=1, pages_per_hour=60` → `minutes=1`; `pages=599, pages_per_hour=60` → `minutes=ceil(35940/60)=599` minutes? recompute: `ceil(599 * 60 / 60) = ceil(599) = 599`; better invariant: `pages=1, pages_per_hour=600 → ceil(60/600) = ceil(0.1) = 1`, asserts the ceiling kicks in for sub-minute reads). Use `session` + `client` fixtures from `tests/conftest.py:90` exactly as `test_reading_speed_service.py` does.
- **`tests/api/test_estimate.py`** — happy path (200 with the synthetic IdP minting `reading-speed:read` JWT + a pre-seeded row via PUT), 412 unset, 403 wrong scope, 422 invalid input (parametrize `0`, `-1`, `-100`, missing, `"thirty"`, `1.5`), 422 sub-injection-via-body, 401 no JWT, cross-user isolation (`test_cross_user_isolation_estimate` mirroring `test_cross_user_isolation_put_then_get` from `test_reading_speed.py:224`), speed-changes-yield-different-estimate, the float-coercion behavior for `pages: 600.0` (Story 3.3 CR2 pinned Pydantic v2's lax-int-coercion of whole floats — mirror that test here for `pages` so a future tightening is caught).

**Coverage threshold:** `coverage of src/resource_server/api/estimate.py, src/resource_server/services/estimate_service.py, and src/resource_server/services/duration.py is ≥90%`. Verify with:

```sh
uv run pytest \
  --cov=src/resource_server/api/estimate \
  --cov=src/resource_server/services/estimate_service \
  --cov=src/resource_server/services/duration \
  --cov-report=term-missing
```

Capture the per-file table in the Dev Agent Record. If any file is below 90%, add targeted tests rather than excluding lines — the surface is too small to justify exclusions.

### AC13 — Static + lint + format + type gates remain green

`uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, and `uv run pytest -q` all exit 0 from `services/resource-server/`. The RS's `CLAUDE.md` mandates all four gates before every commit; this story does not relax any of them. Capture transcripts in Debug Log References.

## Tasks / Subtasks

- [x] **Task 1 — Create `services/duration.py` with `format_duration` helper** (AC: #1, #2)
  - [x] 1.1 New file `src/resource_server/services/duration.py`. Add module docstring referencing UX-DR18 (the ux-design-specification examples at lines 232, 250, 478) and pinning the include-minutes rule for the `≥ 1440` case.
  - [x] 1.2 Define `_PREFIX = "≈"` as a module-level constant (U+2248).
  - [x] 1.3 Implement `format_duration(minutes: int) -> str` matching the AC2 boundary table. Raise `ValueError` on `minutes < 0`. Defensive `"≈ 0 m"` for `minutes == 0`. Split into days / hours / minutes and join the non-zero components with `" "` (e.g., `[f"{d} d", f"{h} h", f"{m} m"]` filtered to non-zero).
  - [x] 1.4 Type-hint as `int -> str`; no `float` accepted.

- [x] **Task 2 — Tests: `tests/services/test_duration.py`** (AC: #2, #12)
  - [x] 2.1 Create the test file with a parametrized happy-path test covering every row from AC2's boundary table verbatim (use `pytest.mark.parametrize`; tuple of `(minutes, expected)`).
  - [x] 2.2 Add a single-row test for the `0 → "≈ 0 m"` defensive case.
  - [x] 2.3 Add a `pytest.raises(ValueError)` test for `-1`.
  - [x] 2.4 Add a purity test asserting two calls with the same input return identical strings.
  - [x] 2.5 Run `uv run pytest tests/services/test_duration.py -v` and confirm all rows pass.

- [x] **Task 3 — Create `api/schemas/estimate.py`** (AC: #1, #7, #9)
  - [x] 3.1 New file `src/resource_server/api/schemas/estimate.py`. Mirror the shape of `api/schemas/reading_speed.py`: `from __future__ import annotations`, `BaseModel`, `ConfigDict`, `Field` imports.
  - [x] 3.2 Define `EstimateIn(BaseModel)`: `model_config = ConfigDict(extra="forbid")`, `pages: int = Field(ge=1)`. Docstring documents the `ge=1` boundary, the `extra="forbid"` rationale (identity is JWT-only, body-level `sub` is rejected at the boundary as 422), and references `reading_speed.py`'s same pattern.
  - [x] 3.3 Define `EstimateOut(BaseModel)`: `minutes: int`, `formatted: str`. Docstring references architecture line 696 (the two-field side-by-side convention).

- [x] **Task 4 — Create `services/estimate_service.py`** (AC: #1, #3, #6, #10)
  - [x] 4.1 New file `src/resource_server/services/estimate_service.py`. Module docstring documents the rounding rule (`math.ceil(n * 60 / p)`), the reuse of `reading_speed_service.get_for_user`, and the deliberate return-DTO-not-entity choice (vs. `reading_speed_service`).
  - [x] 4.2 `async def compute_for_user(session: AsyncSession, sub: str, pages: int) -> EstimateOut`:
    - Call `await reading_speed_service.get_for_user(session, sub)` — propagate `ReadingSpeedUnsetError`.
    - Compute `minutes = math.ceil(pages * 60 / row.pages_per_hour)`. Cast to `int` after `ceil` (which returns `int` on Python ≥ 3.10 but pin explicitly: `int(math.ceil(...))`).
    - Return `EstimateOut(minutes=minutes, formatted=format_duration(minutes))`.
  - [x] 4.3 Imports: `math`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from resource_server.api.schemas.estimate import EstimateOut`, `from resource_server.services import reading_speed_service`, `from resource_server.services.duration import format_duration`.

- [x] **Task 5 — Tests: `tests/services/test_estimate_service.py`** (AC: #3, #6, #10, #12)
  - [x] 5.1 Create the test file. Pattern: mirror `tests/services/test_reading_speed_service.py:18` — use the `session` fixture, seed via `reading_speed_service.upsert`, call `estimate_service.compute_for_user`, assert.
  - [x] 5.2 `test_compute_for_user_happy_path` — `pages_per_hour=30`, `pages=600` → `EstimateOut(minutes=1200, formatted="≈ 20 h")`.
  - [x] 5.3 `test_compute_for_user_raises_reading_speed_unset_when_row_absent` — `pytest.raises(ReadingSpeedUnsetError)` on a `sub` with no row.
  - [x] 5.4 `test_cross_user_isolation` — seed two rows with different `pages_per_hour`, call `compute_for_user` for each, assert `minutes` reflects each user's own speed.
  - [x] 5.5 `test_ceiling_round_up_partial_minute` — `pages_per_hour=600`, `pages=1` → `minutes=1` (raw is `0.1`, ceiling is `1`).
  - [x] 5.6 `test_returns_dto_not_entity` — assert the result is `EstimateOut` (not `ReadingSpeed`) and has the two expected fields only. Pins the deliberate-return-shape choice.

- [x] **Task 6 — Create `api/estimate.py` router** (AC: #1, #3, #4, #5, #6, #8)
  - [x] 6.1 New file `src/resource_server/api/estimate.py`. Mirror the layout of `api/reading_speed.py:1-47`: docstring, `from __future__ import annotations`, imports, `router = APIRouter(tags=["estimate"])`.
  - [x] 6.2 Single `@router.post("/estimate", response_model=EstimateOut)` handler. Body: `payload: EstimateIn`; `session: Annotated[AsyncSession, Depends(get_session)]`; `principal: Annotated[Principal, Depends(require_scope("reading-speed:read"))]`. Body: `return await estimate_service.compute_for_user(session, principal.subject, payload.pages)`.
  - [x] 6.3 Module docstring should reference architecture §C3 line 386 (the wire-contract) and architecture §C1 line 361 (`/v1/estimate` is a versioned domain API).

- [x] **Task 7 — Register estimate router in `api/v1/__init__.py`** (AC: #1)
  - [x] 7.1 Open `src/resource_server/api/v1/__init__.py`. Currently:
    ```python
    from fastapi import APIRouter
    from resource_server.api.reading_speed import router as reading_speed_router

    router = APIRouter(prefix="/v1")
    router.include_router(reading_speed_router)
    ```
  - [x] 7.2 Add `from resource_server.api.estimate import router as estimate_router` and `router.include_router(estimate_router)` after the existing `include_router` line. Preserve alphabetic order: `estimate_router` before `reading_speed_router`.

- [x] **Task 8 — Tests: `tests/api/test_estimate.py`** (AC: #1, #4, #5, #6, #7, #8, #9, #10, #11, #12)
  - [x] 8.1 Create the test file. Mirror the structure of `tests/api/test_reading_speed.py:1-332` exactly: `synthetic_rs_idp` fixture from `build_synthetic_rs_idp(monkeypatch)`, `_auth_header(token)` helper, `_make_token(idp, sub=..., scope=...)` helper.
  - [x] 8.2 **Test fixtures pattern:** for tests that need a seeded `reading_speeds` row, mint a `reading-speed:write` token, `PUT /v1/reading-speed`, then mint a `reading-speed:read` token for the same `sub` and call `POST /v1/estimate`. Mirror `test_get_returns_200_with_pages_per_hour_when_row_exists:41` from `test_reading_speed.py`.
  - [x] 8.3 `test_post_estimate_200_with_minutes_and_formatted` — AC4: seed `pages_per_hour=30`, post `{"pages": 600}`, assert response is exactly `{"minutes": 1200, "formatted": "≈ 20 h"}`.
  - [x] 8.4 `test_post_estimate_412_when_reading_speed_unset` — AC6: no PUT, post `{"pages": 600}` with read scope, assert 412 with full envelope `{"errorCode": "reading_speed_unset", "message": "Reading speed not set for this user", "detail": None}`.
  - [x] 8.5 `test_post_estimate_403_when_only_write_scope` — AC5: mint a `reading-speed:write` token (no read), post, assert 403 `forbidden_scope`.
  - [x] 8.6 `test_post_estimate_422_invalid_input_*` — AC7: parametrize over `[0, -1, -100]`, `[missing-field, "thirty", 1.5]`, and `[[], "hello", 42]` (non-object body). For each, assert `response.status_code == 422` and `body["errorCode"] == "invalid_input"`. Also assert `"input" not in entry` for each entry in `body["detail"]` (sanitization mirror).
  - [x] 8.7 `test_post_estimate_401_no_jwt` — AC8: no `Authorization` header, post, assert 401 `session_expired`.
  - [x] 8.8 `test_post_estimate_401_expired_jwt` — AC8: mint with `exp_offset_seconds=-1`, post, assert 401 `session_expired`.
  - [x] 8.9 `test_post_estimate_401_wrong_audience` — AC8: mint with `aud="wrong-audience"`, post, assert 401 `session_expired`.
  - [x] 8.10 `test_post_estimate_422_rejects_unknown_fields_including_sub` — AC9: post `{"pages": 600, "sub": "victim-sub"}` with read scope and seeded row, assert 422 `invalid_input` AND `body["detail"]` contains at least one entry with `type == "extra_forbidden"`. Mirror Story 3.3 CR1 test at `test_reading_speed.py:267`.
  - [x] 8.11 `test_cross_user_isolation_estimate` — AC10: seed two users with `pages_per_hour=30` and `60`, post `{"pages": 600}` for each, assert each gets `minutes` matching their own row (1200 vs 600).
  - [x] 8.12 `test_speed_change_yields_different_estimate` — AC11: seed `pages_per_hour=30`, post `{"pages": 600}` → 1200 minutes. PUT `pages_per_hour=60`, post again → 600 minutes. Assert `r2["minutes"] < r1["minutes"]`.
  - [x] 8.13 `test_post_estimate_accepts_whole_float_pages_as_int` — Story 3.3 CR2 mirror: `pages: 600.0` succeeds with `minutes=1200`; `pages: 1.5` is 422. Pin Pydantic v2's lax-int-coercion behavior so a future `Field(strict=True)` change is caught.

- [x] **Task 9 — Coverage verification** (AC: #12)
  - [x] 9.1 Run `uv run pytest --cov=src/resource_server/api/estimate --cov=src/resource_server/services/estimate_service --cov=src/resource_server/services/duration --cov-report=term-missing`.
  - [x] 9.2 Confirm each of the three files reports ≥90% line coverage in the terminal table.
  - [x] 9.3 If any file is below 90%, add targeted tests (do NOT add `# pragma: no cover` exclusions — the surface is too small).
  - [x] 9.4 Capture the per-file coverage table in the Dev Agent Record's Debug Log References.

- [x] **Task 10 — Static + lint + format + type gates** (AC: #13)
  - [x] 10.1 From `services/resource-server/`: `uv run ruff check` → exit 0; transcript captured.
  - [x] 10.2 `uv run ruff format --check` → exit 0; transcript captured.
  - [x] 10.3 `uv run ty check` → exit 0 with zero errors and zero warnings (per RS `CLAUDE.md` mandate); transcript captured. If `ty` flags `int(math.ceil(...))` as redundant on Python 3.14, leave the cast (defense against a future `from __future__ import …` change to `math.ceil`'s return type narrowing) and document the choice in Completion Notes.
  - [x] 10.4 `uv run pytest -q` → exit 0 with no warnings escalation; full RS suite green. The Story-3.3 suite must remain green (we're adding new tests, not modifying existing ones).

- [x] **Task 11 — Commit pacing per RS CLAUDE.md** (AC: #13)
  - [x] 11.1 Per `services/resource-server/CLAUDE.md`: commit frequently at every point of stability, with Conventional Commits messages (no scope). Suggested cadence:
    - C1: `feat: add format_duration helper + boundary table tests` (Tasks 1, 2 green)
    - C2: `feat: add EstimateIn/EstimateOut schemas` (Task 3 green)
    - C3: `feat: add estimate_service.compute_for_user + tests` (Tasks 4, 5 green)
    - C4: `feat: add POST /v1/estimate endpoint + register on /v1 router + request-layer tests` (Tasks 6, 7, 8 green)
    - C5: `chore: capture coverage + static-gate transcripts` (Tasks 9, 10 green, transcripts in Dev Agent Record)
  - [x] 11.2 Before each commit: re-run all four gates (ruff check, ruff format --check, ty check, pytest). Do NOT commit on a red gate.

## Dev Notes

### What this story is — and is not

**Is:** A pure-RS story landing the `/v1/estimate` endpoint + `estimate_service` + `format_duration` helper + their tests. Three new source files (`services/duration.py`, `services/estimate_service.py`, `api/estimate.py`), one new schemas file (`api/schemas/estimate.py`), three new test files (`tests/services/test_duration.py`, `tests/services/test_estimate_service.py`, `tests/api/test_estimate.py`), one router registration line added to `api/v1/__init__.py`. Zero changes outside `services/resource-server/`.

**Is NOT:** Any BFF code (Story 4.2 owns the proxy + `ResourceServerClient.compute_estimate`), any SPA code (Story 4.3 owns `EstimateCell`), any new `AppError` discriminated-union variant (4.3 adds `reading_speed_unset` to the SPA's union — the RS already has the wire code from Story 3.3), any Alembic migration (no DB-schema change; the estimate is computed in-memory from the existing `reading_speeds` row + the request's `pages`), any Compose / Dockerfile / Playwright change (Stories 3.6 and 4.4 own those surfaces), any test-reset extension (3.4 already truncates `reading_speeds`; no new RS state to truncate).

### Why the service returns the DTO instead of the entity

`reading_speed_service.get_for_user` returns `ReadingSpeed` (the SQLModel entity) and the router constructs `ReadingSpeedOut(pages_per_hour=row.pages_per_hour)`. The convention is: services return entities, routers construct DTOs.

`estimate_service.compute_for_user` deliberately breaks that convention because the "formatted" string is a presentation-format concern that is cleaner to colocate with the (minutes, formatted) pair. The router becomes a pure pass-through:

```python
return await estimate_service.compute_for_user(session, principal.subject, payload.pages)
```

instead of:

```python
result = await estimate_service.compute_for_user(session, principal.subject, payload.pages)
return EstimateOut(minutes=result.minutes, formatted=format_duration(result.minutes))
```

The second shape would duplicate the formatting call between the service and the router (or hide the helper at the router level — worse). The chosen shape keeps formatting concerns inside the service module and tests them as a unit. **Document this in `estimate_service.py`'s module docstring** so a future contributor doesn't "fix" the asymmetry.

### Input bounds and integer overflow

The architecture pragmatically caps `pages` at "any positive int up to int64" (Pydantic's default int range), and `pages_per_hour` is currently bounded only by `Field(ge=1)` (no upper bound). Defended work item **D66** in `_bmad-output/implementation-artifacts/deferred-work.md:578` explicitly tags Story 4.1 as the first real-world exposure of degenerate inputs:

> "A malicious or buggy client posting `pages_per_hour=999999999999` is persisted and later read back; downstream Story 4.1 estimate math (`pages / pages_per_hour * 60`) would yield a tiny 'minutes' value (~0) and the formatted-duration helper would return `"≈ 0 m"`. Real fix: `Field(ge=1, le=10000)`. **Belongs to:** Story 4.1 (where degenerate inputs become user-visible) or a security-review pass."

**Decision for v1: defer the `le=10000` bound; do NOT add it in this story.** Rationale:

1. The `le=10000` belongs on `ReadingSpeedUpsert.pages_per_hour` (Story 3.3's schema), not on `EstimateIn.pages`. Adding it here changes the wrong field.
2. Adding it to `ReadingSpeedUpsert` is a Story-3.3 contract change that needs Story 3.5's BFF proxy + Story 3.5's SPA `SettingsPage` validator to update in lock-step. That's a multi-file story-spanning change.
3. The `≈ 0 m` defensive return in `format_duration` (AC2's edge case) covers the user-visible symptom without breaking the contract.
4. Story 5.2 (security review) is the right place to either land the `le` cap or document the deferred-risk explicitly.

Surface this in Completion Notes as "D66 deferred per spec; defensive `format_duration(0) -> '≈ 0 m'` covers the user-visible symptom." Do NOT add the `le` in passing.

For `pages`: the SPA's book-create form allows arbitrary positive integers (Story 2.5 verified). A user posting `pages=999999999999` with a reasonable `pages_per_hour=30` produces `minutes = ceil(999999999999 * 60 / 30) = 1999999999998` — `format_duration` would emit `"≈ 1388888888 d 21 h 18 m"`. Strange but not a crash, and Story 4.4's J3 happy-path uses `pages=600`. Do not add a `le` on `pages` either — same multi-file argument applies.

### The `≈` character — encoding and grep-ability

The leading character is **U+2248 ALMOST EQUAL TO** (`≈`), not `~` or `≃`. The UX spec at `ux-design-specification.md:232,250,478` uses this exact character. Pin via module-level constant `_PREFIX = "≈"` so:

1. A future contributor can grep `"≈"` to find the format-string source.
2. A future contributor who accidentally copy-pastes a look-alike (e.g., `≃` U+2243 or `~` U+007E) breaks the boundary tests, not silently emits the wrong character.

Save the file as UTF-8 (Python 3 default). The RS's `pyproject.toml` and existing source files are UTF-8; no encoding declaration needed.

### Source tree components to touch

```
services/resource-server/
├── src/resource_server/
│   ├── api/
│   │   ├── estimate.py                  # NEW — POST /v1/estimate router
│   │   ├── schemas/
│   │   │   └── estimate.py              # NEW — EstimateIn, EstimateOut
│   │   └── v1/
│   │       └── __init__.py              # MODIFY — register estimate_router
│   └── services/
│       ├── duration.py                  # NEW — format_duration helper
│       └── estimate_service.py          # NEW — compute_for_user
└── tests/
    ├── api/
    │   └── test_estimate.py             # NEW
    └── services/
        ├── test_duration.py             # NEW
        └── test_estimate_service.py     # NEW
```

Six new files, one one-line modification.

### Files being read (not modified) for context

| File | Why | Lines of interest |
|---|---|---|
| `src/resource_server/api/reading_speed.py` | Layout pattern for the new router | 1-47 (whole file) |
| `src/resource_server/services/reading_speed_service.py` | `get_for_user` raises `ReadingSpeedUnsetError` — reused | 24-30 |
| `src/resource_server/api/schemas/reading_speed.py` | `ReadingSpeedUpsert` `extra="forbid"` pattern + `ge=1` | 20-37 |
| `src/resource_server/core/exceptions.py` | `ReadingSpeedUnsetError` definition | 19-27 |
| `src/resource_server/core/errors.py` | `ErrorCode` enum + handlers | 1-97 |
| `src/resource_server/auth/oidc_bearer.py` | `require_scope(...)` dependency factory | 130-156 |
| `src/resource_server/api/v1/__init__.py` | Router registration pattern | whole file (6 lines) |
| `tests/conftest.py` | `session`, `client` fixtures + monkeypatched OIDC env | 90-111 |
| `tests/auth/synthetic_idp.py` | `build_synthetic_rs_idp(monkeypatch)` + `make_access_token` | whole file (224 lines) |
| `tests/api/test_reading_speed.py` | Mirror for request-layer test structure | 1-332 (whole file) |
| `tests/services/test_reading_speed_service.py` | Mirror for service-layer test structure | 1-87 (whole file) |

**No file in this list is modified by Story 4.1 except `api/v1/__init__.py` (Task 7) and Story 3.3's existing files remain untouched.**

### Architecture references

| Concern | Source | Line(s) |
|---|---|---|
| Wire contract for `POST /v1/estimate` | architecture.md §C3 | 386 |
| `/v1/estimate` is a versioned domain API on RS | architecture.md §C1 | 361 |
| All RS endpoints read identity from JWT only | architecture.md §C3 | 388 |
| Two-field side-by-side `minutes` + `formatted` | architecture.md §"Format Patterns" | 696 |
| One service module per domain | architecture.md §"Structural Patterns" | 613 |
| Distinct DTOs from ORM models | architecture.md §C7 | 418 |
| `ErrorCode` enum (READING_SPEED_UNSET = 412, FORBIDDEN_SCOPE = 403, INVALID_INPUT = 422, SESSION_EXPIRED = 401) | architecture.md §C5 | 396-409 |
| Pessimistic UI for cross-service requests (estimate) — informs `EstimateCell` (Story 4.3), not RS | architecture.md §"Process Patterns" | 91 |
| HTTP status table — 412 specifically for `reading_speed_unset` precondition | architecture.md §"Format Patterns" | 686 |

### UX references

| Concern | Source | Line(s) |
|---|---|---|
| Formatted duration shape (`"≈ 4 h 20 m"`, `"≈ 12 m"`, `"≈ 1 d 2 h"`) | ux-design-specification.md | 232 |
| SPA renders `formatted` verbatim from the response | ux-design-specification.md | 250, 478 |
| UX-DR18 reference in the original AC | epics.md §"Story 4.1" | 1538 |

### Architectural-boundary self-check before implementation

The RS's `services/resource-server/CLAUDE.md` mandates this check at every point of stability. Re-read these constraints before each commit:

1. **`AUTH_TYPE` boundary:** the RS in this story's test suite uses `AUTH_TYPE=none` per `tests/conftest.py:13` (with the synthetic IdP monkeypatched per-test). Do NOT change `AUTH_TYPE` at test time; do NOT modify the `.env.example` `AUTH_TYPE` default. Story 3.6 already activates `AUTH_TYPE=oidc_bearer` for the e2e overlay; that's the only place the flip is documented.

2. **No HTTPException raises in business code:** the architecture (lines 735–749) and RS exception conventions (Story 3.3 CR2 verdict) require all domain failures to raise `AppException` subclasses. `estimate_service.compute_for_user` raises nothing of its own — it propagates `ReadingSpeedUnsetError` from `reading_speed_service`. The router raises nothing — `Pydantic` raises `RequestValidationError` for 422, `require_scope` raises `AppException(FORBIDDEN_SCOPE)`, `get_authenticated_principal` raises `AppException(SESSION_EXPIRED)`. All paths are envelope-handled by existing `app_exception_handler` / `validation_exception_handler`.

3. **No identity from body/path/query:** verified via `EstimateIn`'s `extra="forbid"` + the router's `principal.subject` read. **Pin this in the test suite (AC9)** — a future code change cannot silently weaken `extra="forbid"` without failing the test.

4. **No cross-service Python imports:** RS does not import anything from `services/bff/` or `spa/`. The synthetic-IdP harness lives entirely within `services/resource-server/tests/`. Verified — no `bff` or `services.bff` import shows up in the story's new files.

5. **No new technology/library:** the story uses `math`, `fastapi`, `pydantic`, `sqlalchemy.ext.asyncio`, `sqlmodel`, `pytest`, `pyjwt[crypto]`, `cryptography` — all already in `pyproject.toml`. No new dependency.

### Coverage approach — measure what changed

The `pyproject.toml` `[tool.pytest.ini_options]` uses `addopts = "--strict-markers -ra"` without a default `--cov`. Story 4.1's coverage verification is a one-shot per-file measurement (AC12 / Task 9), not a global enforcement. The Epic 5 Story 5.1 will land the coverage gates as a global concern; this story's job is to make sure the three NEW files start at ≥90% so they don't pull the global number down.

If `pytest-cov` reports coverage gaps on the three new files, add targeted tests rather than adjusting `[tool.coverage.report] omit`. The surface is too small to justify exclusions (helper is ~30 lines, service is ~15 lines, router is ~15 lines).

### Testing standards summary

- **Framework:** pytest + pytest-asyncio (`asyncio_mode = "auto"` per `pyproject.toml:81`).
- **Database:** in-memory SQLite via `StaticPool` (per `tests/conftest.py:75-87`); per-test session reset.
- **HTTP:** `httpx.AsyncClient` with `ASGITransport(app=app)` (per `tests/conftest.py:101-110`).
- **Auth:** `build_synthetic_rs_idp(monkeypatch)` mints in-process RS256 JWTs; `_make_token(idp, sub=..., scope=...)` is the per-test convenience.
- **Test class style:** module-level `async def test_*` functions, no `TestCase` classes (matches Story 3.3 pattern at `tests/api/test_reading_speed.py:41`).
- **Parametrize:** prefer over loop-with-assert for clear failure attribution (mirrors Story 3.3 CR2's `@pytest.mark.parametrize("bad_value", [0, -1, -100])` at `test_reading_speed.py:149`).
- **Response assertion shape:** assert the **full envelope** for first-of-kind error codes (412, 403, 401, 422) — `assert response.json() == {"errorCode": "...", "message": "...", "detail": None}`. For subsequent tests of the same code, assert only `body["errorCode"]` to keep tests readable. Mirror `test_get_returns_412_reading_speed_unset_when_row_absent:63` from `test_reading_speed.py`.

### Project Structure Notes

The story aligns 1:1 with architecture's directory layout at `architecture.md:961-1007`:

- `api/estimate.py` is named exactly as architecture line 971 prescribes.
- `services/estimate_service.py` is named exactly as architecture line 976 prescribes.
- `api/schemas/estimate.py` follows the Story-3.3-established convention (schemas live under `api/schemas/`, not under the archetype's vestigial `models/dto/v1/` — Story 3.3's dev log documents the choice).
- `services/duration.py` is **not** explicitly listed in architecture's directory tree, but a one-file helper under `services/` is the natural home and matches the architectural-style verdict "one service module per domain concept" — `duration` is a formatting domain. **Document this placement in the new file's module docstring.**
- Test files mirror source files: `tests/api/test_estimate.py`, `tests/services/test_estimate_service.py`, `tests/services/test_duration.py`. Architecture lines 1000-1004 prescribe `tests/api/test_estimate.py` and `tests/services/test_estimate_service.py` explicitly; `test_duration.py` is the natural mirror for the new helper.

No conflicts or variances.

### Previous story intelligence (Story 3.3 — done)

Story 3.3 landed:

- `reading_speed_service.get_for_user(session, sub) -> ReadingSpeed` — **reuse exactly** in `estimate_service.compute_for_user`. Story 4.1 does NOT duplicate the SELECT.
- `ReadingSpeedUnsetError(AppException)` at `core/exceptions.py:19-27` — Story 4.1 propagates this; the existing `app_exception_handler` maps to 412. No new error class.
- `ErrorCode.READING_SPEED_UNSET`, `ErrorCode.INVALID_INPUT`, `ErrorCode.FORBIDDEN_SCOPE`, `ErrorCode.SESSION_EXPIRED` — Story 4.1 uses all four through existing plumbing. **No new ErrorCode enum value.**
- `ReadingSpeedUpsert.model_config = ConfigDict(extra="forbid")` — Story 3.3 CR1 added this to defend against body-level `sub` injection. **Story 4.1 MUST mirror this on `EstimateIn`** — same threat model, same defense.
- `validation_exception_handler` sanitizes the `input` field per Story 3.3 CR2 + Story 1.3 P3 — Story 4.1 inherits this for free; AC7's `"input" not in entry` assertion verifies the sanitization holds for the new endpoint.
- Pydantic v2 lax-int-coercion of whole floats (`30.0 -> 30`) — Story 3.3 CR2 pinned this for `pages_per_hour`. **Mirror the test for `pages`** (AC8.13 / Task 8.13).

### Previous story intelligence (Story 3.6 — done)

Story 3.6 prepared the e2e compose profile + helpers but landed NO RS code. The RS suite was static-gate green at the close of 3.6 (`uv run pytest -q` reported all green). Story 4.1's starting point is fda53fc (merged Epic 3 into main).

Note: Story 3.6's `compose/app.e2e.yml` flips `AUTH_TYPE=oidc_bearer` on the e2e overlay — Story 4.1's NEW endpoint will be exercised under the real `oidc_bearer` validation when Story 4.4's J3 spec runs against `just e2e-up`. Story 4.1 itself does not run e2e specs (Story 4.4 owns J3 / J6). But the implementation must satisfy `oidc_bearer` validation end-to-end, not just the synthetic-IdP harness.

### Git intelligence summary

Recent commits and what they imply for Story 4.1:

- `fda53fc Merge branch 'epic-3' — Stories 3.1-3.6 (RS scaffold → J4 E2E)` — Story 4.1's baseline. Epic 3 RS surface is fully landed and tested.
- `ef0c6d4 chore(3.6): code review — P1–P3 applied, mark done, log D103–D112` — D103-D112 are e2e-harness polish items, not RS-side. None block Story 4.1.
- `73cbfea retro E2` — Epic 2 retrospective; action items A1/A2/A3 are SPA-side. None block Story 4.1.
- `fc041da chore(3.6): create story` — Story 3.6 spec creation. Confirms the create-story → dev-story → code-review cadence Story 4.1 will follow.

No git-history surprises. Story 4.1 starts from a clean Epic 3 close.

### Latest tech information

- **Python 3.14** (per `pyproject.toml:9`). `math.ceil` returns `int` on Python ≥ 3.10 (PEP 3141 + `__ceil__` integer narrowing). Explicit `int(math.ceil(...))` is redundant per typing on 3.14 but defensible as defensive — keep the cast.
- **Pydantic v2** (via `fastapi>=0.135.1` transitively pulls `pydantic>=2`). `Field(ge=1)` is enforced at the boundary; `ConfigDict(extra="forbid")` rejects unknown fields as `extra_forbidden`-type validation errors (Story 3.3 CR1 verified).
- **FastAPI ≥ 0.135.1** — `Annotated[T, Depends(...)]` is the supported pattern (verified throughout the RS codebase). `Annotated[Principal, Depends(require_scope("..."))]` is the idiom.
- **pyjwt[crypto] ≥ 2.10,<3** — version-pinned at `pyproject.toml:18`. The synthetic-IdP harness uses `cryptography` (transitively via the `[crypto]` extra) for RSA keygen — already available.
- **SQLModel ≥ 0.0.37** — `Field(ge=1)` is supported at the boundary via the underlying Pydantic v2 integration. Story 4.1 uses Pydantic `BaseModel` for DTOs (not SQLModel), so this is incidentally relevant — the entity-vs-DTO split was Story 3.3's choice and Story 4.1 mirrors it.
- **No new dependency required** — the helper uses `math` (stdlib), the service uses `sqlalchemy.ext.asyncio.AsyncSession` (already in the RS), the router uses `fastapi`, `pydantic`, `resource_server.auth.oidc_bearer.require_scope`, `resource_server.core.database.get_session`. All present.

### References

- [Source: epics.md#Story 4.1: RS — POST /v1/estimate endpoint + estimate_service + format_duration helper] (lines 1522-1577)
- [Source: epics.md#Epic 4: Reading-Time Estimate & Honest Failure (J3, J6)] (lines 1518-1521)
- [Source: architecture.md#C3. Resource Server endpoints] (lines 380-388)
- [Source: architecture.md#C5. ErrorCode enum additions] (lines 396-409)
- [Source: architecture.md#C7. JSON serialization] (line 418)
- [Source: architecture.md#Format Patterns] (line 696 — `minutes` + `formatted` two-field convention)
- [Source: architecture.md#Complete Project Directory Structure] (lines 968-1004 — RS directory tree including `api/estimate.py`, `services/estimate_service.py`, `tests/api/test_estimate.py`, `tests/services/test_estimate_service.py`)
- [Source: PRD.md#FR-ESTIMATE-01 — Per-book reading-time estimate] (line 68)
- [Source: PRD.md#J3. Request a reading-time estimate] (line 99)
- [Source: ux-design-specification.md#"≈ 4 h 20 m" / "≈ 12 m" / "≈ 1 d 2 h" examples] (lines 232, 250, 478)
- [Source: deferred-work.md#D66 — No upper bound on pages_per_hour] (line 578 — deferred per dev notes "Input bounds and integer overflow")
- [Source: implementation-artifacts/3-3-rs-reading-speed-model-migration-v1-reading-speed-get-put-scope-gated.md] (DOC body — the `extra="forbid"` + sanitization patterns Story 4.1 mirrors)
- [Source: services/resource-server/src/resource_server/api/reading_speed.py] (lines 1-47 — router pattern Story 4.1 mirrors)
- [Source: services/resource-server/src/resource_server/services/reading_speed_service.py] (lines 24-30 — `get_for_user` reused by Story 4.1)
- [Source: services/resource-server/src/resource_server/api/schemas/reading_speed.py] (lines 20-37 — `extra="forbid"` + `ge=1` pattern Story 4.1 mirrors)
- [Source: services/resource-server/src/resource_server/core/exceptions.py] (lines 19-27 — `ReadingSpeedUnsetError` propagated by Story 4.1)
- [Source: services/resource-server/src/resource_server/auth/oidc_bearer.py] (lines 130-156 — `require_scope("reading-speed:read")` dependency factory)
- [Source: services/resource-server/tests/conftest.py] (lines 75-111 — `session` + `client` fixtures Story 4.1's tests use)
- [Source: services/resource-server/tests/auth/synthetic_idp.py] (lines 92-139 — `make_access_token(sub=..., scope=...)` Story 4.1's tests use)
- [Source: services/resource-server/tests/api/test_reading_speed.py] (lines 1-332 — request-layer test mirror for Story 4.1)
- [Source: services/resource-server/CLAUDE.md] (the four-gate commit policy Story 4.1 follows)

### Review Findings

Generated by `code-review` on 2026-05-17 against commit `19cb3f8` (baseline `fda53fc`). Three layers (Acceptance Auditor, Blind Hunter, Edge Case Hunter) returned 23 findings; triaged to 6 patches, 6 defers, 5 dismissals.

**Patches (unchecked — awaiting fix):**

- [x] [Review][Patch] **Float-precision in `compute_for_user` — switch to integer math** [services/resource-server/src/resource_server/services/estimate_service.py:61] — `int(math.ceil(pages * 60 / row.pages_per_hour))` coerces to float; for `pages * 60` above 2^53 (~9×10^15) the float quantization makes the ceiling wrong. Integer math is exact and removes the dead `int(...)` cast. Fix: `minutes = (pages * 60 + row.pages_per_hour - 1) // row.pages_per_hour`; drop `import math`. (Med, blind+edge)
- [x] [Review][Patch] **Tautological float-coercion assertion** [services/resource-server/tests/api/test_estimate.py:381] — `int(whole_float * 60 / 60)` cancels to `int(whole_float)`; the assertion would pass even if the RS returned `payload.pages` verbatim. Pin literal expected per parametrized row instead. (Med, blind)
- [x] [Review][Patch] **`_PREFIX` literal `≈` should use Unicode escape** [services/resource-server/src/resource_server/services/duration.py:23] — A look-alike substitution (smart-quotes filter, BOM transcoder) would compile silently and surface only when boundary tests run. Switch to `_PREFIX = "≈"`; non-ambiguous in any encoding. (Low, edge)
- [x] [Review][Patch] **Sanitization assertion only on one 422 test** [services/resource-server/tests/api/test_estimate.py:152-156] — Story Task 8.6 says "Also assert `\"input\" not in entry` for each entry in `body[\"detail\"]`" across the 422 family. Currently only `test_post_estimate_422_on_non_positive_pages` enforces it; the missing-field / wrong-type / float / non-object tests omit it. Add the loop to each. (Low, auditor)
- [x] [Review][Patch] **`EstimateOut.minutes` missing `Field(ge=0)` invariant** [services/resource-server/src/resource_server/api/schemas/estimate.py:42] — A future formula regression that produces negative `minutes` would 500 inside `format_duration` rather than fail as a contract violation on the response side. Adding `Field(ge=0)` (or `ge=1` matching impossibility) pins the invariant. (Low, edge)
- [x] [Review][Patch] **403 test doesn't assert full envelope** [services/resource-server/tests/api/test_estimate.py:128-129] — Spec testing-standards say "assert the full envelope for first-of-kind error codes" (403 is first-of-kind for this endpoint). A regression dropping `message` or `detail` would not be caught. Extend to full `{"errorCode", "message", "detail"}` match. (Low, blind)

**Deferred (pre-existing or out-of-scope polish):**

- [x] [Review][Defer] **Additional 401 negative variants (wrong-scheme, empty-bearer, missing-aud) not pinned for `/v1/estimate`** [services/resource-server/tests/api/test_estimate.py] — AC8 explicit carve-out: "the full negative-scope is already exercised in `tests/auth/test_oidc_bearer.py` — Story 4.1 trusts that and tests the wired-up `/v1/estimate` only on the no-header + expired paths." Defer as test-quality polish. (Low, auditor+blind+edge)
- [x] [Review][Defer] **Service emits no logs on `reading_speed_unset` propagation** [services/resource-server/src/resource_server/services/estimate_service.py] — Useful breadcrumb but the story spec doesn't require it, and Story 3.3's `get_reading_speed` is silent for the same reason. Cross-endpoint logging pattern is its own pass. (Low, edge)
- [x] [Review][Defer] **`_make_token` `**kwargs: object` defeats type-checking** [services/resource-server/tests/api/test_estimate.py:39-46] — The `ty: ignore[invalid-argument-type]` papers over the weakness; a typo like `exp_offset=...` (vs `exp_offset_seconds=...`) would compile silently. Real fix: narrow the kwargs or forward only the keys tests use. (Low, blind+edge)
- [x] [Review][Defer] **AC9 doesn't pin "row not consulted on sub-injection"** [services/resource-server/tests/api/test_estimate.py:269-289] — Spec acknowledges this as future-facing only relevant if `extra="forbid"` regresses. Defer. (Low, blind)
- [x] [Review][Defer] **No-auth + bad-body ordering test not pinned** [services/resource-server/tests/api/test_estimate.py] — FastAPI's dependency-vs-body validation order is stable in practice; defensive against a future regression. Defer. (Low, edge)
- [x] [Review][Defer] **Float-coercion test uses `pages_per_hour=60` vs spec's `30` worked example** [services/resource-server/tests/api/test_estimate.py:355-377] — The lax-coercion invariant is still pinned correctly via the parametrized inputs. Worked-example mismatch only; defer as cosmetic alignment. (Low, auditor)

**Dismissed:**

- `format_duration` post-divmod could return `"≈ "` with empty `parts` — unreachable: early-return on `minutes == 0` is in place; for `minutes ≥ 1`, divmod arithmetic guarantees at least one of `(days, hours, mins)` is non-zero. (blind)
- Test fixture cross-test leakage concern — verified `tests/conftest.py:90-98` is function-scoped + drop_all/create_all teardown; per-test isolation is sound. (blind)
- `int(math.ceil(...))` dead cast — subsumed by Patch #1 (will be removed when switching to integer math). (blind)
- `test_speed_change_yields_different_estimate` over-relies on `expire_on_commit=True` — the fixture is already `expire_on_commit=False`; `upsert()` calls `await session.refresh(row)` explicitly, so the identity-map row is always current. False positive. (edge)
- pytest collection-count observation (15 base × parametrize = 23 collected) — informational only, no defect. (auditor)

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) — `claude-opus-4-7[1m]`

### Debug Log References

**Task 1+2 — `format_duration` helper + boundary tests:**

```
$ uv run pytest tests/services/test_duration.py -v
collected 14 items
tests/services/test_duration.py::test_format_duration_boundary_table[1-≈ 1 m] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[12-≈ 12 m] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[60-≈ 1 h] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[61-≈ 1 h 1 m] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[260-≈ 4 h 20 m] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[1440-≈ 1 d] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[1441-≈ 1 d 1 m] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[1500-≈ 1 d 1 h] PASSED
tests/services/test_duration.py::test_format_duration_boundary_table[2780-≈ 1 d 22 h 20 m] PASSED
tests/services/test_duration.py::test_format_duration_zero_defensive PASSED
tests/services/test_duration.py::test_format_duration_raises_on_negative[-1] PASSED
tests/services/test_duration.py::test_format_duration_raises_on_negative[-60] PASSED
tests/services/test_duration.py::test_format_duration_raises_on_negative[-1440] PASSED
tests/services/test_duration.py::test_format_duration_is_pure PASSED
14 passed in 0.01s
```

**Task 4+5 — `estimate_service.compute_for_user` + service tests:**

```
$ uv run pytest tests/services/test_estimate_service.py -v
collected 6 items
tests/services/test_estimate_service.py::test_compute_for_user_happy_path PASSED
tests/services/test_estimate_service.py::test_compute_for_user_raises_reading_speed_unset_when_row_absent PASSED
tests/services/test_estimate_service.py::test_cross_user_isolation PASSED
tests/services/test_estimate_service.py::test_ceiling_round_up_partial_minute PASSED
tests/services/test_estimate_service.py::test_returns_dto_not_entity PASSED
tests/services/test_estimate_service.py::test_speed_change_yields_different_estimate PASSED
6 passed in 0.07s
```

**Task 6+7+8 — `POST /v1/estimate` router + registration + request-layer tests:**

```
$ uv run pytest tests/api/test_estimate.py -v
collected 23 items
... 23 PASSED (3× 401-paths, 3× 422 non-positive parametrize, 3× 422 float parametrize,
                3× 422 non-object parametrize, 3× 200 whole-float parametrize, 1× 200 happy,
                1× 412 unset, 1× 403 wrong-scope, 1× 422 missing, 1× 422 wrong-type,
                1× 422 sub-injection, 1× cross-user, 1× speed-change)
23 passed in 2.68s
```

**Task 9 — Per-file coverage:**

```
$ uv run pytest tests/api/test_estimate.py tests/services/test_estimate_service.py \
                 tests/services/test_duration.py \
                 --cov=resource_server.api.estimate \
                 --cov=resource_server.services.estimate_service \
                 --cov=resource_server.services.duration \
                 --cov-report=term-missing

Name                                               Stmts   Miss  Cover   Missing
--------------------------------------------------------------------------------
src/resource_server/api/estimate.py                   13      0   100%
src/resource_server/services/duration.py              19      0   100%
src/resource_server/services/estimate_service.py      10      0   100%
--------------------------------------------------------------------------------
TOTAL                                                 42      0   100%
Required test coverage of 90.0% reached. Total coverage: 100.00%
43 passed in 2.30s
```

All three new files at **100%** — well above the AC12 ≥90% threshold; no exclusions.

**Task 10 — Static + lint + format + type gates:**

```
$ uv run ruff check
All checks passed!

$ uv run ruff format --check
94 files already formatted

$ uv run ty check
All checks passed!

$ uv run pytest -q
324 passed, 1 warning in 8.80s
```

The single warning is the pre-existing `InsecureKeyLengthWarning` from `tests/auth/test_oidc_bearer.py::test_token_with_alg_hs256_returns_401` (HMAC short-key test seed; not introduced by Story 4.1).

### Completion Notes List

- **All 12 ACs satisfied:**
  - AC1 — Router + service + schemas + helper all present at the spec-prescribed paths; `estimate_router` registered before `reading_speed_router` (alphabetic) in `api/v1/__init__.py`.
  - AC2 — `format_duration` boundary table fully covered; include-minutes-when-days-present rule pinned (`2780` → `"≈ 1 d 22 h 20 m"`). Defensive `format_duration(0)` returns `"≈ 0 m"`. `ValueError` on negatives.
  - AC3 — `math.ceil(pages * 60 / pages_per_hour)` rounding rule implemented; service returns the `EstimateOut` DTO directly (deliberate asymmetry vs. `reading_speed_service`, documented in the module docstring).
  - AC4 — Happy path verified: `{30, 600}` → `{1200, "≈ 20 h"}`.
  - AC5 — 403 `forbidden_scope` via `require_scope("reading-speed:read")` — wired-up behavior tested.
  - AC6 — 412 `reading_speed_unset` propagates from `reading_speed_service.get_for_user` — full envelope asserted.
  - AC7 — 422 `invalid_input` covered for: non-positive ints, missing field, wrong type (string), fractional float, non-object body. `input`-field sanitization asserted (BFF Story 1.3 P3 / Story 3.3 CR2 mirror).
  - AC8 — 401 `session_expired` covered for: no header, expired token, wrong audience.
  - AC9 — 422 + `extra_forbidden` on body-level `sub` injection — exact mirror of Story 3.3 CR1 test.
  - AC10 — Cross-user isolation: two seeded users get distinct estimates from their own rows.
  - AC11 — Speed change yields strictly smaller `minutes` after PUT — verified at both service and request layer.
  - AC12 — Coverage 100% on all three new files; full suite 324/324 passes; no regressions.

- **D66 deferred per spec.** Dev Notes "Input bounds and integer overflow" called for deferring the `pages_per_hour le=10000` cap; the defensive `format_duration(0) → "≈ 0 m"` covers the user-visible symptom. No `le` added on `EstimateIn.pages` or `ReadingSpeedUpsert.pages_per_hour`. Story 5.2 (security review) is the right place to either land the cap or document the deferred-risk explicitly.

- **`ty` warning suppressed once** on `idp.make_access_token(**kwargs)` in `tests/api/test_estimate.py:46` — the kwargs are typed `object` and ty cannot prove they match the typed positional/keyword arguments of `make_access_token`; the call sites pass legal kwargs (`exp_offset_seconds`, `aud`) verified at runtime. The `# ty: ignore[invalid-argument-type]` is a minimal-scope suppression consistent with the RS CLAUDE.md mandate ("do not add blanket suppressions unless justified and documented").

- **Service docstring documents the deliberate return-shape asymmetry** with `reading_speed_service` (entity-vs-DTO). `test_returns_dto_not_entity` pins it so a future contributor who "fixes the asymmetry" trips the test.

- **No new dependency.** Only stdlib `math` was added; `fastapi`, `pydantic`, `sqlalchemy`, `pyjwt`, `pytest` were all already in `pyproject.toml`.

- **No file outside `services/resource-server/` was touched.** Verified via `git status`. The story is RS-only by design; Stories 4.2 / 4.3 / 4.4 own the cross-service surface.

### File List

**New files:**

- `services/resource-server/src/resource_server/api/estimate.py` — `POST /v1/estimate` router (`require_scope("reading-speed:read")`)
- `services/resource-server/src/resource_server/api/schemas/estimate.py` — `EstimateIn` (`ge=1`, `extra="forbid"`) + `EstimateOut` (`minutes`, `formatted`)
- `services/resource-server/src/resource_server/services/duration.py` — `format_duration(minutes)` helper (UX-DR18 with U+2248 prefix)
- `services/resource-server/src/resource_server/services/estimate_service.py` — `compute_for_user(session, sub, pages) -> EstimateOut`
- `services/resource-server/tests/services/test_duration.py` — boundary-table + edge cases (14 tests)
- `services/resource-server/tests/services/test_estimate_service.py` — service-layer tests (6 tests)
- `services/resource-server/tests/api/test_estimate.py` — request-layer tests (23 tests)

**Modified files:**

- `services/resource-server/src/resource_server/api/v1/__init__.py` — registered `estimate_router` alongside `reading_speed_router`
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `epic-4 backlog → in-progress`, `4-1-* backlog → ready-for-dev → in-progress → review`

### Change Log

| Date | Change | Rationale |
|---|---|---|
| 2026-05-17 | Added `POST /v1/estimate` endpoint (RS) + `estimate_service.compute_for_user` + `format_duration` helper + three test files | Story 4.1 — lands the marquee architectural interaction's RS surface. Reuses `reading_speed_service.get_for_user`; propagates `ReadingSpeedUnsetError` → 412; gates via `require_scope("reading-speed:read")` → 403; `EstimateIn.extra="forbid"` rejects body-level `sub` injection as 422. All 12 ACs satisfied; 100% coverage on the three new files; full RS suite 324/324 green; ruff/ruff-format/ty all clean. |
| 2026-05-17 | Code review — 6 patches applied (P1-P6) | P1: switched `compute_for_user` to exact integer-math ceiling (`(pages * 60 + p - 1) // p`); removes float-precision risk above 2^53. P2: replaced tautological float-coercion assertion with literal expected minutes (now seeds `pages_per_hour=30` matching the spec's worked example). P3: switched `_PREFIX` to explicit `≈` escape. P4: extended `input`-field sanitization assertion across the full 422 family (missing / wrong-type / float / non-object / sub-injection). P5: added `Field(ge=0)` to `EstimateOut.minutes`. P6: 403 test now asserts the full `{errorCode, message, detail}` envelope. 6 defer items recorded as D113–D118 in `deferred-work.md`. Post-patch: 324/324 tests green; 100% per-file coverage; ruff/ruff-format/ty all clean. |
