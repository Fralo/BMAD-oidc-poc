# Story 1.12: BFF `POST /v1/test/reset` endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer running E2E tests,
I want the BFF to expose a guarded `POST /v1/test/reset` endpoint that truncates the auth-related tables,
so that each E2E test can start from a known clean state without manual cleanup or fragile inter-test ordering.

## Acceptance Criteria

**AC1 — Module surface.** A new module `services/bff/src/bff/api/test_reset.py` is created. It exports a `router: APIRouter` and a registration helper `register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None` that is invoked from `services/bff/src/bff/main.py` AFTER the existing `app.include_router(v1_router)` call (main.py:65). The helper is the ONLY place that decides whether the route is registered, and it does so by reading `cfg.enable_test_reset` (already declared at `services/bff/src/bff/core/config.py:95`, default `False`). When `enable_test_reset` is `False` OR `cfg.test_reset_token` is empty/whitespace-only, the function returns without registering anything (defense-in-depth: a missing/empty token is treated the same as `ENABLE_TEST_RESET=false`). When both gates pass, the function calls `app.include_router(router)` so the route is mounted at `/v1/test/reset`. NO new top-level packages; NO change to the `auth_router` / `me_router` / `v1_router` surface; NO Alembic migration; NO new dependencies in `pyproject.toml`. [Source: epics.md#Story 1.12 lines 674–680; architecture.md#Source-Tree Structure line 903; architecture.md#Operational Details "POST /v1/test/reset (e2e profile only)" lines 1354–1360; services/bff/src/bff/main.py:64–65; services/bff/src/bff/core/config.py:95–96.]

**AC2 — Gating: route NOT registered when `ENABLE_TEST_RESET` is unset or any value other than `"true"`.** Given the BFF starts with `ENABLE_TEST_RESET` unset OR set to any value that pydantic-settings does NOT coerce to boolean `True` (i.e., the resulting `cfg.enable_test_reset` is `False`), `register_test_reset_router` is a no-op. **Then** the FastAPI app has NO route matching `/v1/test/reset` and ANY HTTP method against `/v1/test/reset` returns the same `404` envelope that any other unknown route returns on this BFF — Starlette's default `{"detail": "Not Found"}` body with `Content-Type: application/json` (the BFF does NOT install a custom 404 handler in this story; it inherits FastAPI's default). The CSP / SecurityHeaders middleware behavior for unknown paths is unchanged. [Source: epics.md#Story 1.12 lines 675–677; epics.md#Story 1.12 lines 693–695; architecture.md#Operational Details lines 1356, 1360; services/bff/tests/middleware/test_security_headers.py:68–72 (existing evidence that `/v1/<unknown>` returns 404 today with no envelope-handler installed).]

**Implementation note (AC2):** pydantic-settings coerces `"true"` / `"True"` / `"1"` to `True` and everything else to `False` for `bool` fields (this is BaseSettings v2 default behavior). The story does NOT change this — the AC2 wording "any value other than `\"true\"`" is in service of operator clarity; mechanically the code reads `cfg.enable_test_reset` as a Python `bool` and the env-string parsing is handled by pydantic-settings.

**AC3 — Gating: route IS registered when `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` is set.** Given the BFF starts with `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` non-empty, `register_test_reset_router` calls `app.include_router(router)`. **Then** `POST /v1/test/reset` is mounted and visible in the OpenAPI schema. The startup-time log line `test_reset_route_registered` is emitted at INFO level so an operator inspecting logs can verify the gate fired. [Source: epics.md#Story 1.12 lines 679–680.]

**AC4 — Bearer auth: 401 on missing `Authorization` header.** When `POST /v1/test/reset` is called (route IS registered per AC3) WITHOUT an `Authorization` header at all, **then** the BFF responds **401** with envelope `{"errorCode": "session_expired", "message": "Session expired or not present", "detail": null}` — the same envelope the project emits for missing-session on `/api/me` (`services/bff/src/bff/api/me.py:37–44`). The wire-level errorCode is `session_expired` (lower_snake_case per architecture §C5 / `bff/core/errors.py:20`). NO Set-Cookie headers are emitted on this 401 (this is a test-only endpoint with no session cookies in its model — there's nothing to clear). NO DB writes occur. [Source: epics.md#Story 1.12 lines 682–683; architecture.md#API & Communication Patterns C5 line 403; services/bff/src/bff/core/errors.py:20; services/bff/src/bff/api/me.py:37–44.]

**AC5 — Bearer auth: 401 on wrong bearer token.** When `POST /v1/test/reset` is called with `Authorization: Bearer <wrong-token>` where `<wrong-token>` does NOT match `cfg.test_reset_token`, **then** the BFF responds **401** with the same envelope as AC4. Comparison MUST be constant-time via `hmac.compare_digest(provided_bytes, expected_bytes)` to avoid timing-oracle leaks (same idiom used in `services/bff/src/bff/auth/csrf.py:58–60`). The handler MUST also reject:
- `Authorization` header present but empty.
- `Authorization` header with a non-`Bearer` scheme (e.g., `Basic ...`, `Token ...`).
- `Authorization: Bearer` with NO token value following (e.g., `Bearer ` or `Bearer  `).
- Multiple whitespace-separated values after `Bearer` (e.g., `Bearer foo bar` — reject; only single-token bearer accepted).

All rejection paths emit the same 401 envelope (no enumeration leak in `detail`). NO DB writes occur. A WARN log `test_reset_unauthorized: <classifier>` is emitted with classifier values `missing_header` / `wrong_scheme` / `empty_token` / `token_mismatch` so a real attacker's noise shows up in logs. The bearer string itself is NEVER logged. [Source: epics.md#Story 1.12 lines 685–686; architecture.md#Logging conventions lines 781–788; services/bff/src/bff/auth/csrf.py:58–60.]

**AC6 — Happy path: 204 with empty body + truncation.** When `POST /v1/test/reset` is called with `Authorization: Bearer <token>` where `<token>` matches `cfg.test_reset_token` exactly, **then** the BFF:
1. Executes `DELETE FROM sessions` (truncates all rows). Uses SQLAlchemy `delete(entities.Session)` with no `WHERE` clause AND `execution_options={"synchronize_session": False}` — symmetric with `SessionService.delete_session` at `session_service.py:226–232` (the `synchronize_session=False` was Story 1.4's D31 mitigation for SQLite naive-datetime ORM-evaluator mismatches; it also avoids loading every row into Python memory for the truncate).
2. Executes `DELETE FROM auth_states` (truncates all rows). Same pattern.
3. Commits ONCE (a single `await db.commit()` after BOTH deletes — atomic from the DB's POV). The order is `sessions` first, then `auth_states`. Neither table has a FK to the other (architecture §I5 + Story 1.4's `0001_init` migration), so order is essentially free, but documenting it makes the test ordering deterministic.
4. Logs `test_reset_truncated tables=sessions,auth_states sessions_deleted=<N1> auth_states_deleted=<N2>` at INFO level. The row counts come from `result.rowcount` on each `.execute(...)` (SQLAlchemy returns it for `DELETE` against SQLite).
5. Responds **204 No Content** with an EMPTY body. Implementation: return `Response(status_code=204)` from `fastapi.Response` — FastAPI emits no body and sets `content-length: 0` (same idiom Story 1.7 used for `/auth/logout`).

NO Set-Cookie headers are emitted. NO CSP / security-headers changes — `SecurityHeadersMiddleware` (added in Story 1.6) excludes `/v1/*` from CSP attach per its existing prefix rules, so the 204 response carries NO CSP header (consistent with other JSON API endpoints). [Source: epics.md#Story 1.12 lines 688–690; architecture.md#API & Communication Patterns format patterns line 680; services/bff/src/bff/services/session_service.py:212–239; services/bff/src/bff/middleware/security_headers.py (CSP exclusion for /v1/).]

**Implementation note (AC6):** The story does NOT add a `truncate_test_state` method to `SessionService` — placing the truncate logic inside the handler keeps the "test surface" cleanly isolated from production code paths in `SessionService`. (Story 2.3 will extend the SAME `test_reset.py` to truncate the `books` table; that extension is also handler-local. Story 3.4 adds an analogous endpoint to the RS that does NOT share code with the BFF — there is no cross-service shared module.)

**AC7 — CSRF middleware must NOT reject this route.** `CsrfMiddleware` (Story 1.6, `services/bff/src/bff/auth/csrf.py`) currently enforces double-submit cookie + `X-CSRF-Token` header + same-origin `Origin`/`Referer` on **every** state-changing request (POST/PUT/PATCH/DELETE) without any path exemption (csrf.py:37–38 — only `_SAFE_METHODS` exempted, no path filter). The E2E `resetState` fixture (epics §Story 1.11 line 645) does NOT send `X-CSRF-Token` / `bff_csrf` cookie / matching `Origin` — it sends `Authorization: Bearer ${TEST_RESET_TOKEN}` only. Therefore, **this story extends `CsrfMiddleware.dispatch` to exempt the path `/v1/test/reset` from CSRF enforcement**. The exemption is:
- Implemented as an early-exit check at the top of `dispatch` (immediately after the `_SAFE_METHODS` short-circuit at csrf.py:37–38): `if request.url.path == "/v1/test/reset": return await call_next(request)`.
- Hard-coded path string (not a prefix, not a config var) so a malicious operator can't broaden the exemption by setting a wildcard env var. The path is the same `/v1/test/reset` constant the route is mounted at.
- The exemption is unconditional on `cfg.enable_test_reset` — when the gate is off, the route is NOT registered and the request falls through to FastAPI's 404 default (the CSRF middleware NEVER ran on it in the first place if the request path didn't match anything else; but a malicious POST to that path under the gate-off configuration would still skip CSRF and hit the 404 — that is acceptable because there's no state-change downstream).
- WARN log `csrf_exempt_path path=/v1/test/reset method=<method>` is emitted at the exemption point so the exemption shows in logs (so an operator can audit it).

This middleware change is made HERE rather than in Story 1.6 because: (a) Story 1.6 is already `done`; (b) the route the exemption services does not exist until this story; (c) the exemption is THE coupling between CSRF and this story and belongs with the new route. [Source: epics.md#Story 1.12 (implicit from "Authorization: Bearer" being the only auth shown); services/bff/src/bff/auth/csrf.py:37–38; epics.md#Story 1.11 line 645; sprint-status.yaml 1-6-bff-csrf-middleware-csp-header: done.]

**AC8 — Production (default profile) gating evidence.** Given the existing `compose/app.yml` declares the BFF in profiles `[default, dev, e2e]` (compose/app.yml:36) AND the existing `services/bff/.env.example` carries the lines `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` (.env.example:47–48), **then** for the `default` profile (production-like) NO additional env override is needed — `ENABLE_TEST_RESET=false` is already the baseline. A reviewer inspecting `compose/app.yml` confirms NO `environment:` block sets `ENABLE_TEST_RESET=true` for the `bff` service in the default profile (today it carries none — only an `env_file:` reference). [Source: epics.md#Story 1.12 lines 692–695; compose/app.yml:6–37; services/bff/.env.example:47–48.]

**AC9 — E2E compose profile gating evidence.** Given the existing `compose/app.yml` has a single `bff` service entry that participates in all three profiles via `profiles: [default, dev, e2e]` (compose/app.yml:36), **then** to enable the route under the `e2e` profile this story adds a SECOND service entry `bff-e2e` (or equivalent profile-specific override) that:
- Is scoped to `profiles: [e2e]` ONLY.
- Inherits the base `bff` build / volumes / healthcheck / ports / depends_on (DRY via YAML anchors `&bff-base` + `<<: *bff-base` is acceptable; alternatively, copy-paste with a comment is also acceptable per Story 1.3's `compose/app.yml` style).
- Adds an `environment:` block with `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN=${TEST_RESET_TOKEN:?TEST_RESET_TOKEN is required when e2e profile is up}` (the `:?` form makes the e2e profile fail-fast at `docker compose up` time if the operator forgets to set `TEST_RESET_TOKEN` — closes the Story-1.1 D3 deferred concern that `change-me` placeholders boot silently).
- Removes the base `bff` service from the `e2e` profile so the two are mutually exclusive (change `profiles: [default, dev, e2e]` on the base to `profiles: [default, dev]`).

**Alternative acceptable approach (preferred for minimal diff):** keep the single `bff` service with `profiles: [default, dev, e2e]` AND introduce a profile-conditional `environment:` block via a `services/bff/.env.e2e` file plus a `compose/app.e2e.yml` overlay that the top-level `docker-compose.yml` includes ONLY when `e2e` is active. Either approach satisfies the AC; whichever the dev picks, it MUST be documented in this story's File List with a one-line rationale, and an integration test (AC10) MUST verify the gate fires.

[Source: epics.md#Story 1.12 lines 697–699; deferred-work.md#D3 (`change-me` silent acceptance — this story's AC9 closes it for `TEST_RESET_TOKEN`); compose/app.yml:5–37; docker-compose.yml (top-level `include:` directive).]

**AC10 — Test coverage matrix.** Tests under `services/bff/tests/api/test_test_reset.py` (NEW file — name disambiguated from pytest's `test_*` convention by the doubled prefix; module is `tests/api/test_test_reset.py` so pytest discovers it and the BFF route module is `src/bff/api/test_reset.py`) cover the scenarios enumerated in epic line 702–703, expanded to:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | Route not registered when `ENABLE_TEST_RESET=false` | `monkeypatch.setattr(settings, "enable_test_reset", False)`; rebuild app (helper) | `POST /v1/test/reset` → 404; response body matches FastAPI default `{"detail": "Not Found"}` (or whatever the BFF's unknown-route 404 emits today); other methods (`GET`/`PUT`/`DELETE`) also return 404 |
| 2 | Route not registered when `ENABLE_TEST_RESET=true` but `TEST_RESET_TOKEN` is empty | `enable_test_reset=True, test_reset_token=""` | Same as #1 — 404 on all methods |
| 3 | Route not registered when `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=" "` (whitespace) | `enable_test_reset=True, test_reset_token="   "` | Same as #1 — 404 (defensive: empty-after-strip is treated as missing) |
| 4 | Missing `Authorization` header | gate ON, token=`"secret-xyz"`; POST with no auth header | 401 `{"errorCode": "session_expired", ...}`; WARN log `test_reset_unauthorized: missing_header`; no DB writes (assert row counts unchanged) |
| 5 | Empty `Authorization` header (`Authorization: ""`) | same | 401 `session_expired`; classifier `missing_header` (treat empty-string same as absent) |
| 6 | Non-`Bearer` scheme | `Authorization: Basic dGVzdA==` | 401 `session_expired`; classifier `wrong_scheme` |
| 7 | `Bearer` with no token | `Authorization: Bearer ` or `Authorization: Bearer   ` | 401 `session_expired`; classifier `empty_token` |
| 8 | `Bearer` with wrong token | `Authorization: Bearer wrong-value` | 401 `session_expired`; classifier `token_mismatch`; bearer string NOT in caplog text |
| 9 | `Bearer` with token differing only by trailing whitespace | `Authorization: Bearer secret-xyz ` (trailing space) | 401 `session_expired` (treat trailing whitespace as part of the token; constant-time compare against the raw env value rejects). Classifier `token_mismatch`. |
| 10 | `Bearer` with extra tokens (`Bearer foo bar`) | `Authorization: Bearer foo bar` | 401 `session_expired`; classifier `token_mismatch` (or `wrong_scheme` — pick one and assert consistently; recommend `token_mismatch` since the scheme is correct) |
| 11 | Correct bearer, empty tables | gate ON, no rows seeded; POST with `Bearer secret-xyz` | 204; empty body (`response.content == b""`); `content-length: 0`; row counts pre/post both 0 |
| 12 | Correct bearer, sessions populated | seed 3 `sessions` rows directly via the `session` fixture; POST | 204; sessions count = 0 post; INFO log `test_reset_truncated sessions_deleted=3 auth_states_deleted=0` |
| 13 | Correct bearer, auth_states populated | seed 2 `auth_states` rows; POST | 204; auth_states count = 0; INFO log `... sessions_deleted=0 auth_states_deleted=2` |
| 14 | Correct bearer, BOTH tables populated | seed 5 sessions + 3 auth_states; POST | 204; both counts = 0 post; INFO log reflects 5 / 3 |
| 15 | CSRF exemption — POST without CSRF header / cookie succeeds | gate ON, bearer correct, no `X-CSRF-Token` header, no `bff_csrf` cookie, no `Origin` header | 204 (NOT 403 `csrf_invalid`); WARN log `csrf_exempt_path path=/v1/test/reset method=POST` |
| 16 | CSRF middleware still enforces on OTHER POST paths | sanity check — re-run an existing CSRF test (e.g., the `tests/auth/test_csrf.py` POST-without-token test) to confirm exemption is path-scoped and not global | 403 `csrf_invalid` (no regression) |
| 17 | Idempotent successive calls | gate ON, bearer correct; POST twice in a row | both → 204; both INFO logs emitted; row counts = 0 throughout |
| 18 | Bearer token containing `:` or special characters | gate ON, token=`"!@#$%^&*():_+"`; POST with matching bearer | 204 (no parsing/quoting issues — compared as bytes byte-for-byte) |
| 19 | Bearer token with leading/trailing whitespace in env | `monkeypatch.setattr(settings, "test_reset_token", "  abc  ")`; client POSTs `Authorization: Bearer abc` | 401 `token_mismatch` (env value is compared verbatim; `.strip()` is applied to the env value at gate-evaluation time for "is it empty" only, not for comparison) — **OR** if the dev chooses to `.strip()` the env value globally, then 204. Pick one approach and assert consistently. Recommended: 401 (don't quietly strip secrets). |
| 20 | OpenAPI schema reflects gate | When gate ON, `GET /openapi.json` lists `/v1/test/reset` under paths; when gate OFF, it does NOT | Documented via two tests |
| 21 | INFO log on startup when gate ON | startup hook (lifespan or include-time) emits `test_reset_route_registered` | caplog at INFO captures it once per app build |
| 22 | INFO log NOT emitted when gate OFF | startup with gate OFF | caplog does NOT contain `test_reset_route_registered` |

Coverage of `services/bff/src/bff/api/test_reset.py` AND the new `register_test_reset_router` function AND the CSRF middleware exemption branch is **≥90%** per the project gate `[tool.coverage.report] fail_under = 90` (`services/bff/pyproject.toml:86`). The epic's explicit ask (epics line 704) is ≥90% on `src/bff/api/test_reset.py` — the project-wide gate plus this AC's coverage table satisfies it. [Source: epics.md#Story 1.12 lines 701–704; services/bff/pyproject.toml:86.]

**Implementation note (AC10 — fixtures):** The existing `tests/conftest.py` provides `engine` (session-scoped, in-memory SQLite), `session` (function-scoped AsyncSession with drop+recreate teardown), `client` (ASGI test client with `get_session` dep override), `client_with_csrf` (same + pre-set CSRF cookie/header), and `client_no_redirects` (no auto-follow). Scenario #15 uses the bare `client` (not `client_with_csrf`) and asserts the 204 directly — that proves the exemption is in place even when the client provides no CSRF material. Scenario #16 reuses an existing test from `tests/auth/test_csrf.py` to assert non-regression. Gate-state tests (#1–#3, #20–#22) need a helper that rebuilds the FastAPI app (or, simpler: a parametrized fixture that builds a fresh app instance inside the test and asserts on it without the global `app` singleton). The recommended pattern is a `build_app(enable: bool, token: str) -> FastAPI` helper in `tests/api/test_test_reset.py` that imports the construction logic from `bff.main` (extract it into a `build_app(settings) -> FastAPI` factory if not already done — see Task 1).

**AC11 — Gates remain green.** No new runtime or dev dependencies. From `services/bff/`:
- `uv sync --frozen` → exit 0 (lock untouched).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all prior tests + new test_reset tests pass; total coverage ≥ 90%.
- From repo root: `docker compose --profile default config` → valid; `docker compose --profile e2e config` → valid AND lists the `bff` service with `ENABLE_TEST_RESET=true`; `docker compose build bff` → succeeds (image still builds — no Dockerfile changes).

[Source: epics.md#Story 1.12 line 703; services/bff/pyproject.toml.]

## Tasks / Subtasks

- [ ] **Task 1: (Optional but recommended) Extract `build_app(settings)` factory from `main.py`** (AC: #1, #3, #10 scenarios 1–3, 20–22)
  - [ ] In `services/bff/src/bff/main.py`, refactor module-level construction (currently lines 33–65) into a `def build_app(cfg: AppSettings) -> FastAPI: ...` function. Module-level `app = build_app(settings)` is the public attribute imported by uvicorn / tests.
  - [ ] Keep all existing behaviors identical: CORS conditional (lines 40–48), middleware stack ordering — `SecurityHeadersMiddleware` then `CsrfMiddleware` LIFO (lines 57–58), exception handlers (lines 60–61), routers (lines 62–65).
  - [ ] Add a call to `register_test_reset_router(app, cfg)` AFTER `app.include_router(v1_router)` (line 65). The helper itself decides whether to register (AC1).
  - [ ] Run `uv run pytest tests/ -q` — confirm zero regressions from the refactor (all 289+ existing tests still pass).
  - [ ] **Alternative:** if the factory extraction is judged too invasive, keep module-level construction and call `register_test_reset_router(app, settings)` directly at the bottom of `main.py`. The gate-state tests (AC10 #1–#3, #20–#22) then build a fresh app inside the test via a local helper that mirrors `main.py`'s construction — slightly more duplication but no refactor. Pick one approach and document it in the File List.

- [ ] **Task 2: Author `src/bff/api/test_reset.py`** (AC: #1, #3, #4, #5, #6)
  - [ ] Create file `services/bff/src/bff/api/test_reset.py` with module docstring describing: purpose ("e2e profile test-reset endpoint"), gating (`ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN`), safety ("registered conditionally; production builds omit the route entirely"), and source references (epics §Story 1.12, architecture §"POST /v1/test/reset").
  - [ ] Imports:
    ```python
    import hmac
    import logging
    from typing import Annotated, Final
    from fastapi import APIRouter, Depends, FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    from sqlalchemy import delete as _delete
    from sqlalchemy.ext.asyncio import AsyncSession
    from bff.core.config import AppSettings, settings
    from bff.core.database import get_session
    from bff.core.errors import ErrorCode
    from bff.models import entities
    ```
  - [ ] Module-level constants:
    ```python
    logger = logging.getLogger(__name__)
    router = APIRouter(prefix="/v1", tags=["Test Reset"])
    _TEST_RESET_PATH: Final[str] = "/v1/test/reset"
    _BEARER_PREFIX: Final[str] = "Bearer "
    ```
    Note: the router prefix is `/v1` and the path is `/test/reset` so the full mount is `/v1/test/reset`. Alternative: import the existing `v1_router` from `bff.api.v1` and attach to it — DON'T do that; the conditional registration is cleanest with a fresh `APIRouter`.
  - [ ] Helper `def _settings_dep() -> AppSettings: return settings` (same idiom as `me.py:32–33` and `auth.py`).
  - [ ] Helper `def _unauthorized_response() -> JSONResponse`:
    ```python
    return JSONResponse(
        status_code=ErrorCode.SESSION_EXPIRED.http_status,  # 401
        content={
            "errorCode": ErrorCode.SESSION_EXPIRED.code,
            "message": ErrorCode.SESSION_EXPIRED.message,
            "detail": None,
        },
    )
    ```
  - [ ] Helper `def _classify_auth_failure(auth_header: str | None) -> str | None`:
    - Returns `None` if the header parses to a non-empty bearer token (caller then validates the value).
    - Returns one of `"missing_header"` / `"wrong_scheme"` / `"empty_token"` / `"token_mismatch"` otherwise.
    - Logic:
      - If `auth_header is None` or `auth_header.strip() == ""` → `"missing_header"`.
      - If `not auth_header.startswith("Bearer ")` (case-sensitive — RFC 6750 §2.1 makes the scheme case-insensitive but the project's convention is to match exactly; document this as an accepted simplification) → `"wrong_scheme"`.
      - Strip the prefix → `token = auth_header[len("Bearer "):]`. If `token.strip() == ""` → `"empty_token"`.
      - Else return `None` (token format is valid; caller compares it).
  - [ ] Route handler:
    ```python
    @router.post("/test/reset", status_code=204)
    async def test_reset(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_session)],
        cfg: Annotated[AppSettings, Depends(_settings_dep)],
    ) -> Response:
        auth_header = request.headers.get("authorization")
        classification = _classify_auth_failure(auth_header)
        if classification is not None:
            logger.warning("test_reset_unauthorized: %s", classification)
            return _unauthorized_response()
        # auth_header is guaranteed to start with "Bearer " here
        provided = auth_header[len(_BEARER_PREFIX):]
        expected = cfg.test_reset_token
        if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
            logger.warning("test_reset_unauthorized: token_mismatch")
            return _unauthorized_response()

        # Happy path: truncate sessions then auth_states; single commit
        sessions_result = await db.execute(
            _delete(entities.Session),
            execution_options={"synchronize_session": False},
        )
        auth_states_result = await db.execute(
            _delete(entities.AuthState),
            execution_options={"synchronize_session": False},
        )
        await db.commit()
        logger.info(
            "test_reset_truncated tables=sessions,auth_states "
            "sessions_deleted=%s auth_states_deleted=%s",
            sessions_result.rowcount,
            auth_states_result.rowcount,
        )
        return Response(status_code=204)
    ```
    **Type note:** the `_delete(entities.Session)` / `_delete(entities.AuthState)` calls may need `# type: ignore[arg-type]` to satisfy `ty` (same pattern Session-service uses at `session_service.py:206`). Confirm by running `uv run ty check` and add the comment only if the type-checker complains.
  - [ ] Helper `def register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None`:
    ```python
    if not cfg.enable_test_reset:
        return
    if not cfg.test_reset_token.strip():
        # Defense-in-depth: empty token means "not configured", same as gate off
        logger.warning(
            "test_reset_route_skipped reason=test_reset_token_empty"
        )
        return
    app.include_router(router)
    logger.info("test_reset_route_registered path=%s", _TEST_RESET_PATH)
    ```
  - [ ] Module-level `__all__ = ["router", "register_test_reset_router"]` so the imports from `main.py` are explicit.

- [ ] **Task 3: Wire the registration helper into `main.py`** (AC: #1, #3)
  - [ ] In `services/bff/src/bff/main.py`, add the import:
    ```python
    from bff.api.test_reset import register_test_reset_router
    ```
  - [ ] AFTER `app.include_router(v1_router)` (main.py:65), add `register_test_reset_router(app, settings)`.
  - [ ] If Task 1's `build_app` refactor was taken, the call lives inside `build_app(...)`; otherwise at module scope after the other `include_router` calls. **Important:** the call MUST come AFTER `add_middleware` calls — middleware order is established once at app build time and `include_router` after `add_middleware` is fine (FastAPI's middleware stack is built lazily on first request); but conceptually placing route registration after middleware setup matches the order in `main.py` today.

- [ ] **Task 4: Extend `CsrfMiddleware` to exempt `/v1/test/reset`** (AC: #7, #10 scenarios 15–16)
  - [ ] In `services/bff/src/bff/auth/csrf.py`, add a module-level constant after `_DEFAULT_PORTS` (line 28):
    ```python
    # Paths exempted from CSRF enforcement. Currently only the test-reset
    # endpoint (Story 1.12); the route itself is only mounted when
    # ENABLE_TEST_RESET=true, but the exemption is unconditional — under
    # gate-off configuration, requests to this path fall through to FastAPI's
    # default 404 (the CSRF check never matters because there's no handler).
    _CSRF_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/v1/test/reset"})
    ```
  - [ ] In `CsrfMiddleware.dispatch`, immediately after the `_SAFE_METHODS` early-exit (csrf.py:37–38), add:
    ```python
    if request.url.path in _CSRF_EXEMPT_PATHS:
        logger.warning(
            "csrf_exempt_path path=%s method=%s",
            request.url.path,
            request.method,
        )
        return await call_next(request)
    ```
  - [ ] Update the module docstring (csrf.py:1–11) to mention the exempt path: "POST /v1/test/reset is exempt from CSRF enforcement (Story 1.12); it authenticates via a shared bearer token instead."
  - [ ] Add a test in `services/bff/tests/auth/test_csrf.py` (extend existing) named `test_csrf_exempt_for_test_reset_path` that POSTs to `/v1/test/reset` WITHOUT CSRF cookie/header and asserts the middleware short-circuits (a 404 from FastAPI is acceptable — the route isn't mounted in unit-test mode; what matters is the response is NOT 403 `csrf_invalid`).
  - [ ] Run `uv run pytest tests/auth/test_csrf.py -v` — all prior CSRF tests still pass; new exemption test passes.

- [ ] **Task 5: Author tests `tests/api/test_test_reset.py`** (AC: #2, #4–#6, #10 scenarios 1–22)
  - [ ] Create `services/bff/tests/api/test_test_reset.py`. Module docstring: "Route-level tests for POST /v1/test/reset (Story 1.12). Covers gating, bearer auth, truncation, CSRF exemption."
  - [ ] Imports:
    ```python
    from datetime import UTC, datetime, timedelta
    import pytest
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import select
    from sqlmodel import SQLModel
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from bff.core.config import AppSettings, settings
    from bff.core.database import get_session
    from bff.models import entities
    ```
  - [ ] Helper `async def _build_test_app(cfg: AppSettings) -> tuple[FastAPI, AsyncEngine]` that builds a fresh `FastAPI` app from the current `bff.main.build_app` factory (if Task 1 done) OR mirrors the construction inline. Returns the app + an engine bound to a fresh in-memory SQLite DB for full isolation from the global `app` singleton. Use this for scenarios #1–#3 (gate state varies per test) and #20–#22 (startup-log assertions).
  - [ ] Implement scenarios 1–3 (route not registered):
    - Each test patches `settings.enable_test_reset` and `settings.test_reset_token` to the variant, builds a fresh app, and POSTs `/v1/test/reset`. Asserts `response.status_code == 404`. Also asserts the WARN log from `register_test_reset_router` ("test_reset_route_skipped") is present for #2 and #3 (not for #1 where gate is off cleanly without warn).
  - [ ] Implement scenarios 4–10 (auth failure modes):
    - Use the existing `client` fixture (gate is OFF in conftest by default — `settings.enable_test_reset` is `False` because `.env` is unset). BUT for these tests we NEED the route registered. Two options:
      - (a) Patch `settings.enable_test_reset = True` + `settings.test_reset_token = "secret-xyz"` via `monkeypatch`, then explicitly call `register_test_reset_router(app, settings)` inside the test (since the global `app` was built once at import time with gate off). After the test, `app.include_router` cannot be cleanly UN-done; subsequent tests would see the route. Mitigate by re-importing or by using a `scope="module"` fixture that captures the registration and accepts the cross-test leak as scoped-only.
      - (b) **Recommended:** use the `_build_test_app` helper from Task 5 to build a fresh app per test. The test client wraps the fresh app's ASGI. This is the cleanest isolation.
  - [ ] Implement scenarios 11–14 (happy path + row count assertions):
    - Use the per-test app + per-test session. Seed `sessions` rows directly via `db.add(entities.Session(...))` with valid values (id=token_urlsafe, sub="test-user", access_token="a", refresh_token="r", id_token="i", expires_at=`datetime.now(UTC) + timedelta(hours=1)`, csrf_secret="c"). Seed `auth_states` similarly. POST with bearer. Assert 204 + empty body. Re-query and assert `select(entities.Session).count() == 0`. Capture caplog and assert the INFO `test_reset_truncated` line with the expected counts.
    - **Critical:** the test MUST use the SAME session/engine that the test app's `get_session` dependency yields. Use the existing `engine` + `session` + `client` fixture pattern but override `get_session` to point at the test's fresh DB (the conftest already does this). When building a fresh app inside the test, set up the dep override BEFORE the POST.
  - [ ] Implement scenario 15 (CSRF exemption):
    - Use the bare `client` fixture (no CSRF cookie/header). After enabling the route on a fresh app, POST `/v1/test/reset` with `Authorization: Bearer ${token}` ONLY (no `X-CSRF-Token`, no `bff_csrf` cookie, no `Origin`). Assert 204. Capture caplog: assert `csrf_exempt_path path=/v1/test/reset method=POST` is present at WARN level.
  - [ ] Implement scenario 16 (CSRF non-regression):
    - This is a re-assertion test: confirm POST to `/test/open` (the stub in `tests/conftest.py:50`) without CSRF still returns 403 `csrf_invalid`. This is a no-code-change test — it should already pass — but include it to make the exemption-is-path-scoped claim load-bearing.
  - [ ] Implement scenarios 17–19 (idempotency + edge cases):
    - #17: POST twice, both 204.
    - #18: Set `test_reset_token` to a special-char string via monkeypatch; assert byte-for-byte match works.
    - #19: Set `test_reset_token="  abc  "` (with spaces); POST with `Authorization: Bearer abc` → assert 401 (per AC5 recommended approach: no stripping of secrets).
  - [ ] Implement scenarios 20–22 (OpenAPI + startup logs):
    - #20a: gate ON → `GET /openapi.json` → `"/v1/test/reset"` in `body["paths"]`.
    - #20b: gate OFF → `"/v1/test/reset"` NOT in paths.
    - #21: caplog at INFO during `_build_test_app(gate_on)` → contains `test_reset_route_registered`.
    - #22: caplog during `_build_test_app(gate_off)` → does NOT contain that log line.
  - [ ] Run `uv run pytest tests/api/test_test_reset.py -v --cov=src/bff/api/test_reset` → all new tests pass; coverage of `test_reset.py` ≥ 90%.

- [ ] **Task 6: Update compose for `e2e` profile gating (AC9)**
  - [ ] **Option A (preferred — minimal diff):** edit `compose/app.yml` to:
    1. Change the existing `bff` service `profiles: [default, dev, e2e]` (line 36) to `profiles: [default, dev]`.
    2. Add a new service `bff-e2e` immediately after, with a YAML anchor on the base or copy-paste of the base config, plus:
       ```yaml
       bff-e2e:
         # ... same build / volumes / ports / depends_on / healthcheck as bff ...
         container_name: bff
         environment:
           ENABLE_TEST_RESET: "true"
           TEST_RESET_TOKEN: "${TEST_RESET_TOKEN:?TEST_RESET_TOKEN is required when the e2e profile is up}"
         profiles: [e2e]
       ```
       Note: `container_name: bff` is reused so downstream services (Playwright runner, eventually) addressing `http://bff:8000` work uniformly across profiles.
  - [ ] **Option B (alternative):** keep a single `bff` service with `profiles: [default, dev, e2e]`, and add a sibling file `compose/app.e2e.yml` that uses Compose's merge semantics to ADD an `environment:` block under `services.bff`. Wire it into the top-level `docker-compose.yml` via the `include:` block conditional on the profile — Compose v2 supports profile-scoped includes via a `profiles:` filter on the `include:` entry.
  - [ ] Either way: NO change to `.env.example` is needed (`ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` are already there from Story 1.1). However, document in the story's File List that the operator running `docker compose --profile e2e up` MUST set `TEST_RESET_TOKEN=<real-value>` in their environment / repo-root `.env` (the `:?` form fails fast if missing — closes D3).
  - [ ] Verify:
    - `docker compose --profile default config` → valid; the rendered `bff` service has NO `ENABLE_TEST_RESET=true`.
    - `docker compose --profile e2e config` → valid; the rendered `bff` (or `bff-e2e`) service HAS `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN=<value>`.
    - With `TEST_RESET_TOKEN` unset: `docker compose --profile e2e config` fails with a clear "TEST_RESET_TOKEN is required" message.
  - [ ] Capture command output excerpts in **Debug Log References**.

- [ ] **Task 7: Run the full BFF gate matrix** (AC: #11)
  - [ ] From `services/bff/`:
    - `uv sync --frozen` → exit 0 (no dep changes).
    - `uv run ruff check` → clean.
    - `uv run ruff format --check` → clean.
    - `uv run ty check` → clean. Add `# ty: ignore[...]` comments ONLY if the type-checker objects to the bare `_delete(...)` SQLAlchemy calls — mirror `session_service.py:206`'s existing ignores.
    - `uv run pytest --cov` → all prior tests + new test_reset tests pass; total coverage ≥ 90%.
  - [ ] From repo root:
    - `docker compose --profile default config` → valid.
    - `docker compose --profile e2e config` → valid AND lists `ENABLE_TEST_RESET=true`.
    - `docker compose build bff` → succeeds.
  - [ ] Capture command output excerpts in **Debug Log References**.

- [ ] **Task 8: Update sprint-status + deferred-work**
  - [ ] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `1-12-bff-post-v1-test-reset-endpoint: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] Close `deferred-work.md#D3` for the `TEST_RESET_TOKEN == change-me` half (AC9's `:?` fail-fast). Append a resolution note dated 2026-05-15.
  - [ ] If any new defects surface during implementation, append them as D45+ (or current sequence) in `deferred-work.md` with severity / owner-story / rationale.

## Dev Notes

### What this story is — and is not

**This story implements the BFF's hidden test-reset endpoint: `POST /v1/test/reset`. Behind a two-key gate (`ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` non-empty), it accepts a bearer token, truncates the `sessions` and `auth_states` tables, and returns 204. When the gate is off (default), the route is not registered and any request gets the BFF's standard 404. Production builds (the `default` compose profile) leave the gate off; the `e2e` compose profile turns it on with a required `TEST_RESET_TOKEN`.**

**Explicitly NOT in scope (each is a downstream story OR not part of this story's contract):**

- **No `books` table truncation.** Story 2.3 extends `test_reset.py` to also truncate `books`. The current implementation MUST be structured so 2.3's extension is a one-line addition to the truncate sequence (a new `await db.execute(_delete(entities.Book), execution_options={"synchronize_session": False})` between sessions and auth_states OR after auth_states; pick a stable order). Do NOT pre-emptively add a stub for `books` — Story 2.3's AC includes the schema migration that brings `Book` into existence; this story does not have a `Book` model to reference.
- **No RS test-reset endpoint.** Story 3.4 adds the analogous `/v1/test/reset` on the Resource Server with the same gating shape. There is no shared module across services; 3.4 will copy the gating + bearer-check pattern from this story.
- **No SPA changes.** This is a pure backend story. The Playwright fixtures (Story 1.11) call this endpoint from `e2e/`; that story owns the fixture wiring.
- **No Playwright spec authored.** Story 1.13 (J1 + J5 specs) is the first consumer of this endpoint inside a real test. This story's tests are pytest unit/route tests against the BFF only.
- **No Keycloak truncation.** The endpoint touches BFF-owned tables only. Keycloak user state is reset (when needed) via Keycloak admin REST APIs in a different fixture entirely — out of scope for this story.
- **No CSRF middleware refactor beyond the path exemption.** The exemption is a 3-line addition to `csrf.py`; the rest of the middleware's behavior is untouched. This story does NOT introduce a generic exempt-paths config; the single hard-coded path stays in code so an operator can't broaden it via env.
- **No production-time defense beyond gate-off.** If an operator misconfigures production with `ENABLE_TEST_RESET=true` AND leaks `TEST_RESET_TOKEN`, the route is exploitable. This is documented in PRD §4 "out of scope" — the educational reference does not protect against operator-self-harm. The `services/bff/.env.example` already warns via comments (Story 1.1, .env.example:46 "Story 1.12 — gated by e2e profile").
- **No rate limiting on the endpoint.** Out of scope; trusted bearer auth + path-only exposure is the protection model.

### Dependencies (CRITICAL — read before starting)

**Story 1.4 (`done`)** — owns the `sessions` and `auth_states` SQLModel tables + `0001_init` Alembic migration. This story TRUNCATES those tables; no schema changes.

**Story 1.5 (`done`)** — owns `SessionService.delete_*` methods and the OIDC cookie-session plugin that populates `sessions` rows. This story's truncate is independent of `SessionService` (handler-local DELETE via bare SQLAlchemy `delete()`), but the patterns (`synchronize_session=False`, `_as_utc_aware` handling) come from Story 1.5's work.

**Story 1.6 (`done`)** — owns `CsrfMiddleware`. **This story EXTENDS that middleware** with a path exemption. The middleware is already wired in `main.py:58`. Story 1.6 did NOT install a path-exempt mechanism; this story adds one (a `frozenset({"/v1/test/reset"})` constant + a 4-line early-exit in `dispatch`). Story 1.6's tests in `tests/auth/test_csrf.py` MUST continue to pass; this story adds one new test for the exemption + asserts non-regression on the existing tests.

**Story 1.7 (`done`)** — established the convention of using `fastapi.Response(status_code=204)` for empty-body 204 responses. Reuse that exact pattern.

**Story 1.11 (`backlog`, owned by sprint-status as `1-11-playwright-project-setup-fixtures-helpers`)** — the FIRST consumer of this endpoint from the test side. Story 1.11's `resetState(request, opts)` fixture (epics §Story 1.11 line 645) POSTs to `/v1/test/reset` with `Authorization: Bearer ${process.env.TEST_RESET_TOKEN}`. **This story MUST land before 1.11 starts** (or 1.11 must mark its fixture as a stub until this lands). Per sprint-status order, 1.11 sits BEFORE 1.12 in the YAML — that's a **mild inversion** because 1.11's `resetState` fixture targets the endpoint THIS story creates. The recommended sequencing is: implement 1.12 first (gives 1.11's fixture a real endpoint to call), then 1.11. If 1.11 has already been implemented as a stub, this story closes the dependency and 1.11's E2E run will succeed end-to-end.

**Story 2.3 (`backlog`)** — will EXTEND `test_reset.py` to truncate `books`. Structure this story's truncate sequence so adding `books` is a one-line insertion. Do NOT factor the truncate into a list-of-tables abstraction now — keep it explicit (one `await db.execute(...)` per table) for readability; 2.3 will add its line in the same style.

**Story 3.4 (`backlog`)** — will add a sibling `POST /v1/test/reset` on the Resource Server. NO code shared. The RS will have its own gating + bearer-check; this story's `test_reset.py` is BFF-only.

**Story 1.13 (`backlog`)** — the first SPEC that runs `resetState` against this endpoint. Out of scope for this story.

### Architecture compliance

- **AR32 (epics line 97)** — "Test reset endpoint: `POST /v1/test/reset` on BFF (truncates `books`, `sessions`, `auth_states`) and RS (truncates `reading_speeds`). Available only when `ENABLE_TEST_RESET=true`; requires shared bearer from `TEST_RESET_TOKEN`. Returns 204. Production builds do not register the route." — this story implements the BFF half EXCEPT `books` (deferred to 2.3).
- **Architecture §"POST /v1/test/reset (e2e profile only)" lines 1354–1360** — wire contract: 204 success, 404 when off, bearer required, gated by `ENABLE_TEST_RESET`.
- **Architecture §C5 line 396** — `ErrorCode` enum: `session_expired` is the 401 code used by `/api/me` for missing/invalid session; this story REUSES it for the missing/wrong bearer case (no new `ErrorCode` member needed — there is no `INVALID_TEST_RESET_BEARER` enum member, and adding one would leak that the endpoint exists to attackers via the errorCode differing from a vanilla `/v1/<unknown>` 404).
- **Architecture §C6 line 411** — timeouts: no external HTTP calls in this handler, so timeouts/retries don't apply. The handler only touches the local DB.
- **Architecture §"Logging conventions" lines 781–788** — never log token material; truncate ids to first-8-chars in INFO logs. This handler logs ZERO ids (truncate is a table-wide operation; no per-row context) and ZERO token material. Classifier strings are the only auth-failure context logged.
- **Source-tree (architecture §line 903)** — `src/bff/api/test_reset.py` is the canonical location for the BFF module; `tests/api/test_test_reset.py` is the canonical test location (the doubled `test_test_` prefix is intentional — `test_reset.py` is the production module name, not a test file).

### Library / framework requirements

No new dependencies. All imports are already in the BFF's `pyproject.toml`:
- `fastapi` (already pinned ≥0.x — provides `APIRouter`, `FastAPI`, `Request`, `Response`, `Depends`, `JSONResponse`).
- `sqlalchemy` / `sqlmodel` (already pinned — provides `delete`, `AsyncSession`).
- `hmac` (stdlib — used for constant-time bearer compare).
- `logging` (stdlib).
- No new runtime deps; no new dev deps.

Python 3.14 is the project floor (pyproject.toml:9 `requires-python = ">=3.14"`). Match the existing codebase's style: type annotations everywhere, `Annotated[...]` for `Depends`, `from __future__ import annotations` is NOT used in this codebase (see `me.py`, `auth.py`).

### File structure requirements

**New files:**
- `services/bff/src/bff/api/test_reset.py` — the route module + `register_test_reset_router` helper.
- `services/bff/tests/api/test_test_reset.py` — pytest module covering AC10's 22 scenarios.

**Modified files:**
- `services/bff/src/bff/main.py` — import + call `register_test_reset_router(app, settings)` after `app.include_router(v1_router)`. Optional `build_app(cfg)` factory extraction.
- `services/bff/src/bff/auth/csrf.py` — add `_CSRF_EXEMPT_PATHS` constant + early-exit in `dispatch`. Update module docstring.
- `services/bff/tests/auth/test_csrf.py` — add `test_csrf_exempt_for_test_reset_path` test.
- `compose/app.yml` — add `bff-e2e` service (Option A) OR add `compose/app.e2e.yml` overlay (Option B). Either way, profile-conditional `ENABLE_TEST_RESET=true` + required `TEST_RESET_TOKEN`.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip `1-12-bff-post-v1-test-reset-endpoint` status across the workflow.
- `_bmad-output/implementation-artifacts/deferred-work.md` — append resolution note closing the `TEST_RESET_TOKEN` half of D3.

**NOT modified:**
- `services/bff/src/bff/core/config.py` — `enable_test_reset` and `test_reset_token` are ALREADY declared (config.py:95–96).
- `services/bff/.env.example` — `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` are ALREADY present (.env.example:47–48).
- Alembic migrations — no schema changes.
- `services/bff/pyproject.toml` — no new dependencies.

### Testing standards

- **Framework:** pytest 8+, pytest-asyncio (already pinned per pyproject.toml:39–41).
- **HTTP client:** `httpx.AsyncClient(transport=ASGITransport(app=app))` — same as conftest.
- **DB:** in-memory SQLite via `create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)` — same as conftest.
- **Log assertion:** use pytest's `caplog` fixture; assert on `caplog.records` or `caplog.text`.
- **Coverage gate:** total project `fail_under = 90` (pyproject.toml:86). Per-module ≥90% for `src/bff/api/test_reset.py` per epic line 704.
- **Test naming:** the test file is `tests/api/test_test_reset.py` so pytest discovers it. Inside, prefer top-level `async def test_<scenario>(...)` functions matching the style of `tests/api/test_auth.py` (Story 1.5 / 1.7) — no `class TestX` wrappers unless they add clarity for a sub-group.
- **Lint/format:** `uv run ruff check` and `uv run ruff format --check` must be clean. `uv run ty check` must be clean.
- **Python invocation:** all commands in this story (and any inline scripting in tests) use `python` (not `python3`) per the project convention (CLAUDE.md). The Dockerfile and compose healthchecks already use `python` — no changes needed there.

### Previous story intelligence

**From Story 1.5 review (cookie-session OIDC plugin):**
- Use `set_cookie(value="", max_age=0, ...)` NOT `delete_cookie(...)` to clear cookies. (Not applicable here — this story emits no cookies.)
- `_safe_session_id_log(...)` truncates ids to first-8-chars + `...` when ≥8 chars. (Not applicable here — no per-row ids to log.)

**From Story 1.6 review (CSRF middleware):**
- The middleware sits OUTSIDE `SecurityHeadersMiddleware` in the LIFO stack (main.py:57–58 — `SecurityHeaders` added first, `Csrf` added last → Csrf runs first on entry). A CSRF-403 short-circuit returns BEFORE `SecurityHeaders` runs, which is fine because the 403 JSON body needs no CSP.
- The CSRF middleware uses `hmac.compare_digest` for token comparison (csrf.py:58–60). REUSE the same idiom for bearer-token comparison in this story's handler.
- CSRF middleware logs path + method on every rejection (`csrf_header_missing` / `csrf_token_mismatch` / `csrf_origin_mismatch`). Mirror that style with `test_reset_unauthorized: <classifier>`.

**From Story 1.7 review (logout endpoint):**
- `fastapi.Response(status_code=204)` with NO body argument emits an empty body + `content-length: 0`. REUSE for this story's 204.
- Constant-time compare (`hmac.compare_digest`) needs `bytes` of equal length for true constant-time behavior; a length mismatch leaks one bit (the length) which is acceptable for tokens of fixed length but NOT for bearer tokens of variable length. **For this story:** `hmac.compare_digest(provided_bytes, expected_bytes)` is still the right primitive — Python's implementation pads/truncates safely; a length mismatch returns `False` without leaking byte values. Document this in a code comment.
- Honest-degradation pattern (logout still returns 204 when Keycloak is unreachable) is NOT applicable here — this handler has no external calls.

**From Story 1.9 review (SPA AuthService):**
- AuthService.logout() POSTs to `/auth/logout` (BFF). This story's endpoint is BFF-only and not consumed by the SPA at all — only by Playwright fixtures (Story 1.11).

### Review Findings

- [x] [Review][Patch] Stale forward-pointer comment in `compose/app.yml` [compose/app.yml:23-25] — "Story 1.12 will add ENABLE_TEST_RESET=true..." comment remained after story 1.12 was implemented; updated to past-tense accurate description of the e2e overlay approach.
- [x] [Review][Defer] Non-idiomatic `except ValueError, TypeError:` in `csrf.py` [services/bff/src/bff/auth/csrf.py:103] — pre-existing from Story 1.6; deferred to future style cleanup.
- [x] [Review][Defer] `_build_app` test helper mutates global `settings` singleton before `monkeypatch` scope [services/bff/tests/api/test_test_reset.py:75-76] — low-risk; deferred to test-quality cleanup pass.

### Git intelligence summary

Last 5 commits on `batch-implement-stories`:
- `d77c8d0 Merge branch 'E1S6'` — merged Story 1.6 (CSRF middleware) into the integration branch. This is the merge that ensures `CsrfMiddleware` exists for this story to extend.
- `cc0f532 feat: implement story 1.6` — added `CsrfMiddleware` + `_CSRF_EXEMPT_PATHS` is NOT in 1.6's diff (this story is the first to introduce it).
- `e90a34c feat: implement story 1.7` — added logout endpoint; established the `Response(status_code=204)` pattern and the `hmac.compare_digest` reuse.
- `48f69b5 feat: implement story 1.6` — earlier iteration of 1.6 (squashed into `cc0f532` via the merge).
- `2c2a86c feat: implement story 1.5` — OIDC cookie-session plugin; established `_safe_session_id_log` and the session_service patterns this story implicitly relies on.

**Implication for this story:** Stories 1.6 and 1.7 both touched `src/bff/api/auth.py` and `src/bff/auth/csrf.py`. This story re-touches `csrf.py` (path exemption) but does NOT touch `auth.py`. The integration branch has clean separation; no rebase risk.

### Latest tech information

- **FastAPI** — `app.include_router(router)` is order-independent of `add_middleware` calls; routes added after middleware are still wrapped by it. (Confirmed by FastAPI 0.115+ docs and source — Starlette's `Router` lazily builds the middleware stack on first request.)
- **SQLAlchemy 2.x** — `delete(Table)` without a `WHERE` clause issues a bare `DELETE FROM <table>` SQL statement. SQLite supports this; `result.rowcount` returns the deleted row count. With `execution_options={"synchronize_session": False}`, the ORM's session-sync step is skipped (the same mitigation Story 1.4 documented for SQLite naive-datetime ORM-evaluator issues; harmless here).
- **pydantic-settings 2.x** — `bool` fields from env coerce `"true"` / `"True"` / `"1"` / `"yes"` / `"on"` to `True` and everything else (including `""`, `"false"`, `"0"`) to `False`. This is the v2 default and matches AC2's wording.
- **Starlette** — `BaseHTTPMiddleware` is the parent class for `CsrfMiddleware`; the `dispatch` method receives a `Request` and is expected to return a `Response`. Early-exit `return await call_next(request)` is the documented idiom for path-exemption.
- **pytest-asyncio** — uses `asyncio_mode = "auto"` (default in pyproject.toml-style configs); test functions just need `async def` and pytest discovers them. No `@pytest.mark.asyncio` decorators required (check `pyproject.toml:76` for the `[tool.pytest.ini_options]` section).
- **httpx 0.27+** — `AsyncClient(transport=ASGITransport(app=app))` is the supported pattern for in-process ASGI testing.

### Project Structure Notes

- New file `src/bff/api/test_reset.py` slots cleanly into the existing `api/` package alongside `auth.py`, `me.py`, `health.py`, `v1/`.
- New test file `tests/api/test_test_reset.py` — pytest will discover it via the `test_*.py` convention (the doubled `test_` prefix is fine; the module is `tests.api.test_test_reset` and pytest collects every test function inside).
- The CSRF exemption sits in `src/bff/auth/csrf.py` — same module as the middleware itself. No new sub-module.
- No `src/bff/db/` folder exists today (the architecture's source-tree spec describes a target that the codebase has not fully migrated to — `models/entities/` is the actual current location). This story does NOT introduce `db/` either; it imports `from bff.models import entities` and references `entities.Session` + `entities.AuthState`.

### References

- [Source: epics.md#Story 1.12 lines 666–704] — the entire story spec.
- [Source: epics.md#AR32 line 97] — architectural requirement for the test-reset endpoint.
- [Source: epics.md#Story 1.11 line 645] — `resetState(request, opts)` fixture signature that consumes this endpoint.
- [Source: epics.md#Story 2.3 lines 854–878] — downstream story that extends `test_reset.py` for `books`.
- [Source: epics.md#Story 3.4 lines 1282–1298] — sibling RS endpoint with the same gating shape.
- [Source: architecture.md#"POST /v1/test/reset (e2e profile only)" lines 1354–1360] — operational contract.
- [Source: architecture.md#Source-Tree Structure lines 903, 972] — canonical file paths for BFF + RS `test_reset.py`.
- [Source: architecture.md#API & Communication Patterns C5 lines 396–409] — `ErrorCode` envelope; `session_expired` for 401.
- [Source: architecture.md#Logging conventions lines 781–788] — never log token material.
- [Source: services/bff/src/bff/core/config.py lines 71–96] — `ENABLE_TEST_RESET` / `TEST_RESET_TOKEN` already declared.
- [Source: services/bff/src/bff/auth/csrf.py lines 1–141] — middleware to extend.
- [Source: services/bff/src/bff/api/me.py lines 36–44] — `_session_expired_response()` shape to mirror.
- [Source: services/bff/src/bff/services/session_service.py lines 212–239] — `delete_session` pattern (synchronize_session=False, single commit).
- [Source: services/bff/.env.example lines 46–48] — gating env vars already templated.
- [Source: compose/app.yml lines 5–37] — BFF service definition; profiles include `e2e`.
- [Source: deferred-work.md#D3 lines 27–33] — `change-me` placeholder concern; this story's AC9 closes the `TEST_RESET_TOKEN` half.
- [Source: services/bff/pyproject.toml lines 9, 76–86] — Python 3.14, pytest config, coverage gate.
- [Source: CLAUDE.md] — project convention: `python` (not `python3`).

### Project context reference

Project-context facts loaded at activation:
- BMAD_books accessibility/responsive design: OUT OF SCOPE (not relevant — this is a backend-only story with no UI surface).
- Backend archetype: `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL) — this story stays inside the archetype's conventions (FastAPI APIRouter, SQLModel entities, uv-managed deps).
- Python invocation: `python` (never `python3`) — applies to any inline command examples; the project's Dockerfile, compose healthchecks, and pytest commands already use `python`.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- **Task 1 decision:** took the **alternative** path — no `build_app(cfg)` factory refactor of `main.py`. The new helper `register_test_reset_router(app, settings)` is called once at the bottom of `main.py` after `app.include_router(v1_router)`. Gate-state tests build their own fresh `FastAPI` apps via a local `_build_app` helper in `tests/api/test_test_reset.py` that mirrors `main.py`'s construction (CORS skipped — not exercised by these tests). This keeps `main.py`'s diff to two lines (import + call) and zero risk of regressing the 300-test baseline.
- **Task 4 decision:** added the path-exemption to `services/bff/src/bff/auth/csrf.py` per the story's prescribed shape — `_CSRF_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/v1/test/reset"})` module-level constant + a 4-line early-exit in `CsrfMiddleware.dispatch` immediately after the `_SAFE_METHODS` short-circuit. Logged at WARN with classifier-style format `csrf_exempt_path path=... method=...`.
- **Task 6 decision (AC9):** picked **Option B (overlay file)** — `compose/app.e2e.yml` is a classic compose override applied with the explicit `-f` flag pattern. Tried Option A (sibling `bff-e2e` service inside `compose/app.yml`) first and discovered that compose's `include:` directive at the top-level `docker-compose.yml` is unconditional, so `${TEST_RESET_TOKEN:?...}` interpolation fires on the `default` profile as well — defeating the purpose. The overlay file pattern keeps the fail-fast scoped to e2e invocations: `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up`. The base `bff` service in `compose/app.yml` retains its original `profiles: [default, dev, e2e]` (no diff to its env-var block).
- **Bearer comparison:** uses `hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))` with NO `.strip()` on either side — secrets are compared verbatim. Empty/whitespace `TEST_RESET_TOKEN` is treated as gate-off at registration time (defense-in-depth), but a non-empty token with leading/trailing whitespace IS compared literally; scenario 19 enforces "no silent stripping of secrets".
- **`rowcount` access:** SQLAlchemy `AsyncSession.execute(...)` returns the broad `Result[Any]` static type even though the runtime object is `CursorResult` with `.rowcount`. Used `getattr(result, "rowcount", -1)` to keep `ty` clean without importing `sqlalchemy.engine.CursorResult`.
- **AC1 helper signature:** `register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None` — exactly as specified. `__all__ = ["register_test_reset_router", "router"]`.
- **Coverage:** `src/bff/api/test_reset.py` 54/54 stmts → 100%; project total 97.63% (gate is 90%). Full BFF suite: 328 tests, all green.
- **Gates run from `services/bff/`:**
  - `uv sync --frozen` → exit 0 (no dep changes; pyproject.toml untouched)
  - `uv run ruff check` → All checks passed!
  - `uv run ruff format --check` → 65 files already formatted (clean)
  - `uv run ty check` → All checks passed!
  - `uv run pytest --cov` → 328 passed, 97.63% coverage
- **Compose gates run from repo root:**
  - `docker compose --profile default config` → valid; `bff` service environment shows `ENABLE_TEST_RESET=false`.
  - `TEST_RESET_TOKEN=test-token-abc docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → valid; `bff` service environment shows `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=test-token-abc`.
  - `env -i HOME=$HOME PATH=$PATH docker compose -f docker-compose.yml -f compose/app.e2e.yml --env-file /dev/null --profile e2e config` → fails fast with `required variable TEST_RESET_TOKEN is missing a value: TEST_RESET_TOKEN is required when the e2e profile is up`.
  - `docker compose build bff` → image built successfully.
- **Python invocation convention:** all command examples and inline documentation written in this story (story file, code docstrings, README-style comments in `compose/app.e2e.yml`) use `python` — never `python3` — per `CLAUDE.md`. The existing Dockerfile / compose healthchecks / pytest commands already followed this convention; nothing changed.

### File List

**New files (created by this story):**
- `services/bff/src/bff/api/test_reset.py` — `POST /v1/test/reset` handler + `register_test_reset_router(app, cfg)` helper + `_classify_auth_failure` / `_unauthorized_response` helpers. Module docstring describes purpose, gating, auth, safety, and source references.
- `services/bff/tests/api/test_test_reset.py` — pytest module covering all 22 AC10 scenarios. Doubled `test_` prefix is intentional (pytest discovers it; the BFF route module is `test_reset.py` without the prefix). Helper `_build_context(enable, token)` builds a fresh `FastAPI` app + in-memory SQLite engine per test for full isolation.
- `compose/app.e2e.yml` — `e2e` profile override that adds `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=${TEST_RESET_TOKEN:?...}` to the `bff` service. Applied with `-f compose/app.e2e.yml` flag; NOT in the top-level `include:` (compose's include is unconditional and would fail-fast even on the default profile).

**Modified files:**
- `services/bff/src/bff/main.py` — added `from bff.api.test_reset import register_test_reset_router` import and a single `register_test_reset_router(app, settings)` call after `app.include_router(v1_router)` (line 65).
- `services/bff/src/bff/auth/csrf.py` — added `_CSRF_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/v1/test/reset"})` module-level constant and a 4-line early-exit in `CsrfMiddleware.dispatch` immediately after the `_SAFE_METHODS` short-circuit. Updated module docstring to mention the exemption.
- `services/bff/tests/auth/test_csrf.py` — added one new test `test_csrf_exempt_for_test_reset_path` that POSTs `/v1/test/reset` without CSRF material on the live `bff.main:app` (where the route is NOT registered) and asserts the response is 404 (not 403) AND the WARN `csrf_exempt_path` log line is present — proves the exemption is path-scoped.
- `compose/app.yml` — header comment updated to point readers at `compose/app.e2e.yml` for the e2e profile override. The base `bff` service definition itself is unchanged.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flipped `1-12-bff-post-v1-test-reset-endpoint: backlog` → `in-progress` → `review`.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended a "Partial resolution" note to D3 closing the `TEST_RESET_TOKEN` half (the `KEYCLOAK_ADMIN_PASSWORD` and `BFF_CLIENT_SECRET` halves remain deferred to their respective stories).

**NOT modified (intentional — per story spec):**
- `services/bff/src/bff/core/config.py` — `enable_test_reset` (line 95) and `test_reset_token` (line 96) were already declared by Story 1.3's archetype-baseline.
- `services/bff/.env.example` — `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` were already present (lines 47–48, Story 1.1).
- `services/bff/pyproject.toml` — no new dependencies.
- Alembic migrations — no schema changes.
