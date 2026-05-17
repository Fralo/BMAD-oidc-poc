---
status: done
story_key: 3-4-rs-post-v1-test-reset-endpoint
epic: 3
prerequisites: 3.1 (done — RS scaffolded, `/health`, `ENABLE_TEST_RESET` + `TEST_RESET_TOKEN` already declared in `AppSettings` at `services/resource-server/src/resource_server/core/config.py:93-94`, project-specific `ErrorCode.SESSION_EXPIRED` at 401 lives in `core/errors.py:27-31`, `app_exception_handler` wired in `main.py:65`); 3.2 (done — `oidc_bearer` plugin per-route `Depends` model, NOT middleware — so the test-reset route's `oidc_bearer` non-application is just an absence of `Depends(require_scope(...))`); 3.3 (done — `ReadingSpeed` SQLModel at `models/entities/reading_speed.py`, `0001_init_init_reading_speeds.py` migration, `__all__ = ["ReadingSpeed"]` in `models/entities/__init__.py` so `SQLModel.metadata` picks it up)
specLoopIteration: 1
---

# Story 3.4: RS — `POST /v1/test/reset` endpoint

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer running E2E tests,
I want the RS to expose a guarded `POST /v1/test/reset` endpoint that truncates the `reading_speeds` table, with the same `ENABLE_TEST_RESET` + `TEST_RESET_TOKEN` gating shape as the BFF's analog (Story 1.12),
so that the J4 (and Epic 4's J3/J6) Playwright specs can rely on a deterministic empty reading-speed state, symmetric with the BFF's clean-slate guarantee on `sessions` / `auth_states` / `books`.

## Acceptance Criteria

**AC1 — Module surface.** A new module `services/resource-server/src/resource_server/api/test_reset.py` is created. It exports a `router: APIRouter` and a registration helper `register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None` that is invoked from `services/resource-server/src/resource_server/main.py` AFTER the existing `app.include_router(v1_router)` call (`main.py:68`). The helper is the ONLY place that decides whether the route is registered, and it does so by reading `cfg.enable_test_reset` (already declared at `services/resource-server/src/resource_server/core/config.py:93`, default `False`). When `enable_test_reset` is `False` OR `cfg.test_reset_token` is empty/whitespace-only OR `cfg.test_reset_token.strip()` equals the literal placeholder `"change-me"` (defense-in-depth: the archetype default ships as `"change-me"` per `.env.example:59`, and accepting that as a real token would let a misconfigured production stack be hosed by anyone reading the public template), the function returns without registering anything. When all three gates pass, the function calls `app.include_router(router)` so the route is mounted at `/v1/test/reset`. NO new top-level packages; NO change to the `health_router` / `v1_router` / `v2_router` surface; NO Alembic migration (the `reading_speeds` table already exists from Story 3.3's `0001_init`); NO new dependencies in `pyproject.toml`. [Source: epics.md#Story 3.4 lines 1282-1314; architecture.md#"POST /v1/test/reset (e2e profile only)" lines 1354-1360; architecture.md#Source-Tree Structure line 972; `services/resource-server/src/resource_server/main.py:65-69`; `services/resource-server/src/resource_server/core/config.py:93-94`; `services/resource-server/.env.example:55-59`.]

**Implementation note (AC1 — placeholder gate):** The BFF's Story 1.12 implemented the gate as `enable_test_reset=True AND test_reset_token.strip() != ""`. The RS goes one defensive step further by ALSO rejecting the literal string `"change-me"` (the archetype/template default). Rationale: the BFF's `.env.example` ships the same placeholder, but the BFF AC text only enforced "non-empty". For the RS we're authoring fresh, so we add the `"change-me"` reject to close the "operator copies `.env.example` to `.env` and forgets to rotate" hole that deferred-work item D3 originally surfaced for `BFF_CLIENT_SECRET`. Document this in the dev log; the BFF can adopt the same tighter check in a follow-up. The WARN log on skip differentiates classifiers: `test_reset_route_skipped reason=test_reset_token_empty` vs `reason=test_reset_token_default_placeholder`.

**AC2 — Gating: route NOT registered when `ENABLE_TEST_RESET` is unset or any value other than `"true"`.** Given the RS starts with `ENABLE_TEST_RESET` unset OR set to any value that pydantic-settings does NOT coerce to boolean `True` (i.e., the resulting `cfg.enable_test_reset` is `False`), `register_test_reset_router` is a no-op. **Then** the FastAPI app has NO route matching `/v1/test/reset` and ANY HTTP method against `/v1/test/reset` returns the standard 404 envelope. Specifically: because the BFF's `app_exception_handler` and `validation_exception_handler` ARE registered, and FastAPI's *default* 404 for unmatched paths returns `{"detail": "Not Found"}` (Starlette default — there is NO project-specific 404 handler today on the RS, same as the BFF), the response body for a `/v1/test/reset` GET/POST/PUT/DELETE while the gate is off is `{"detail": "Not Found"}` at HTTP 404. **This is acceptable**: the RS deliberately does NOT install a custom 404-mapping handler (architecture §C5 line 396 enumerates project-specific error codes; `not_found` is NOT in the RS's list — only `BOOK_NOT_FOUND` is on the BFF). Document this in the dev log. [Source: epics.md#Story 3.4 lines 1290-1292; architecture.md#"POST /v1/test/reset (e2e profile only)" line 1356; `services/resource-server/src/resource_server/core/errors.py:9-46` (no `NOT_FOUND` is a project-specific code emitter); BFF analog at `services/bff/tests/middleware/test_security_headers.py:68-72` (parallel evidence).]

**Implementation note (AC2 — boolean coercion):** pydantic-settings coerces `"true"` / `"True"` / `"1"` / `"yes"` / `"on"` to `True` and everything else (including `""`, `"false"`, `"0"`, `"FALSE"`) to `False` for `bool` fields (BaseSettings v2 default behavior). The story does NOT change this — the AC2 wording "any value other than `\"true\"`" is in service of operator clarity; mechanically the code reads `cfg.enable_test_reset` as a Python `bool` and the env-string parsing is handled by pydantic-settings.

**AC3 — Gating: route IS registered when `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` is set (and not the placeholder).** Given the RS starts with `ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` non-empty AND `TEST_RESET_TOKEN != "change-me"`, `register_test_reset_router` calls `app.include_router(router)`. **Then** `POST /v1/test/reset` is mounted and visible in the OpenAPI schema. The startup-time log line `test_reset_route_registered path=/v1/test/reset` is emitted at INFO level so an operator inspecting logs can verify the gate fired. [Source: epics.md#Story 3.4 lines 1294-1300.]

**AC4 — Bearer auth: 401 on missing `Authorization` header.** When `POST /v1/test/reset` is called (route IS registered per AC3) WITHOUT an `Authorization` header at all, **then** the RS responds **401** with envelope `{"errorCode": "session_expired", "message": "Authentication required", "detail": null}` — the same envelope the RS emits today for missing-bearer on `/v1/reading-speed` (verified at `services/resource-server/src/resource_server/auth/oidc_bearer.py:120-127`, which raises `AppException(ErrorCode.SESSION_EXPIRED)` → 401 via the existing `app_exception_handler`). The wire-level errorCode is `session_expired` (lower_snake_case per architecture §C5 / `core/errors.py:27-31`). NO Set-Cookie headers are emitted (the RS does not use cookies at all — it is stateless OAuth-protected). NO DB writes occur. [Source: epics.md#Story 3.4 lines 1294-1296; architecture.md#API & Communication Patterns C5; `services/resource-server/src/resource_server/auth/oidc_bearer.py:120-127`; `services/resource-server/src/resource_server/core/errors.py:27-31`.]

**AC5 — Bearer auth: 401 on wrong bearer token.** When `POST /v1/test/reset` is called with `Authorization: Bearer <wrong-token>` where `<wrong-token>` does NOT match `cfg.test_reset_token`, **then** the RS responds **401** with the same envelope as AC4. Comparison MUST be constant-time via `hmac.compare_digest(provided_bytes, expected_bytes)` to avoid timing-oracle leaks (same idiom the BFF uses in `services/bff/src/bff/auth/csrf.py:58-60` and that Story 1.12 used at `services/bff/src/bff/api/test_reset.py`). The handler MUST also reject:
- `Authorization` header present but empty.
- `Authorization` header with a non-`Bearer` scheme (e.g., `Basic ...`, `Token ...`, `JWT ...`).
- `Authorization: Bearer` with NO token value following (e.g., `Bearer ` or `Bearer  `).
- Multiple whitespace-separated values after `Bearer` (e.g., `Bearer foo bar` — reject; only single-token bearer accepted).

All rejection paths emit the SAME 401 envelope (no enumeration leak in `detail`). NO DB writes occur. A WARN log `test_reset_unauthorized: <classifier>` is emitted with classifier values `missing_header` / `wrong_scheme` / `empty_token` / `token_mismatch` so a real attacker's noise shows up in logs. The bearer string itself is NEVER logged. [Source: epics.md#Story 3.4 lines 1294-1296; architecture.md#"Logging conventions" lines 781-788; BFF Story 1.12 `services/bff/src/bff/api/test_reset.py` `_classify_auth_failure` helper.]

**AC6 — Happy path: 204 with empty body + truncation.** When `POST /v1/test/reset` is called with `Authorization: Bearer <token>` where `<token>` matches `cfg.test_reset_token` exactly (byte-for-byte; no `.strip()` on either side — the comparison is verbatim, secrets are not silently trimmed), **then** the RS:
1. Executes `DELETE FROM reading_speeds` (truncates all rows). Uses SQLAlchemy `delete(ReadingSpeed)` with no `WHERE` clause AND `execution_options={"synchronize_session": False}` — symmetric with the BFF Story 1.12 pattern. Note: the RS's `services/reading_speed_service.py` does NOT expose a `truncate_all` method, and this story does NOT add one — placing the truncate logic inside the handler keeps the "test surface" cleanly isolated from production code paths in `reading_speed_service`.
2. Commits ONCE (a single `await session.commit()` after the delete — atomic from the DB's POV). There is only ONE table to truncate (`reading_speeds`); contrast the BFF analog which truncates `sessions` then `auth_states` (Story 1.12) and will also truncate `books` after Story 2.3 lands.
3. Logs `test_reset_truncated tables=reading_speeds reading_speeds_deleted=<N>` at INFO level. The row count comes from `result.rowcount` on the `.execute(...)` (SQLAlchemy returns it for `DELETE` against SQLite). **Type note:** `AsyncSession.execute(...)` returns the broad `Result[Any]` static type even though the runtime object is `CursorResult` with `.rowcount`. Use `getattr(result, "rowcount", -1)` to keep `ty` clean without importing `sqlalchemy.engine.CursorResult` (mirrors Story 1.12 dev log line 506).
4. Responds **204 No Content** with an EMPTY body. Implementation: return `Response(status_code=204)` from `fastapi.Response` — FastAPI emits no body and sets `content-length: 0`.

NO Set-Cookie headers are emitted (the RS has no cookie surface at all). NO project-specific 404/422 envelope changes — the handler bypasses the entire `oidc_bearer` per-route `Depends(require_scope(...))` model since it has its OWN auth (the env-bearer check), so neither `SESSION_EXPIRED` nor `FORBIDDEN_SCOPE` is reachable through this route's happy path. [Source: epics.md#Story 3.4 lines 1298-1300; architecture.md#"POST /v1/test/reset (e2e profile only)" lines 1354-1360; BFF Story 1.12 happy-path handler.]

**AC7 — No CSRF / no cookie / no JWT scope-dependency interactions.** Critical contrast with the BFF analog: the RS does NOT have a CSRF middleware to exempt (the BFF's `CsrfMiddleware` is BFF-only because the BFF carries session cookies; the RS is stateless OAuth-resource-server). The RS's `oidc_bearer` JWT-validation surface is wired as **per-route `Depends(require_scope(...))`** (verified at `services/resource-server/src/resource_server/api/reading_speed.py:30-43`), NOT as middleware. Therefore the test-reset route simply DOES NOT add a `Depends(require_scope(...))` dependency — its only auth is the env-bearer check inside the handler body. The route handler `def test_reset(...)` MUST NOT take a `principal: Annotated[Principal, Depends(...)]` parameter. **Concretely:** if a developer attaches a JWT to the test-reset request by mistake, the handler ignores the JWT entirely; if a developer omits the env-bearer, the handler 401s; the `oidc_bearer` plugin does NOT run on this route. [Source: epics.md#Story 3.4 (implicit from "Authorization: Bearer" being the only auth shown and no mention of JWT scopes); architecture.md#"POST /v1/test/reset (e2e profile only)" line 1359 ("require a shared bearer token from `TEST_RESET_TOKEN`"); contrast `services/bff/src/bff/auth/csrf.py:37-38` + Story 1.12's CSRF-exemption block, which is BFF-only.]

**AC8 — Production (default profile) gating evidence.** Given the existing `compose/app.yml` declares the `resource-server` service in profiles `[default, dev]` (compose/app.yml — verified at the RS service block) AND the existing `services/resource-server/.env.example` carries the lines `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` (`.env.example:58-59`), **then** for the `default` profile (production-like) NO additional env override is needed — `ENABLE_TEST_RESET=false` is already the baseline. A reviewer inspecting `compose/app.yml` confirms NO `environment:` block sets `ENABLE_TEST_RESET=true` for the `resource-server` service in the default profile (today it carries none — only an `env_file:` reference). The `register_test_reset_router(app, settings)` call in `main.py` is a no-op when the container boots with the default `.env`. The RS's OpenAPI schema for the `default` profile DOES NOT list `/v1/test/reset`. [Source: epics.md#Story 3.4 lines 1306-1309; `compose/app.yml` RS service block; `services/resource-server/.env.example:55-59`.]

**AC9 — E2E compose profile wiring is DEFERRED to Story 3.6.** The epic text at lines 1302-1304 explicitly states: *"the changes land here as part of Story 3.6, but the endpoint exists from this story"*. **This story does NOT modify `compose/app.yml` or `compose/app.e2e.yml`.** Story 3.6 owns adding the `resource-server` service to the `e2e` profile (today it is in `[default, dev]` only — verified at `compose/app.yml`), wiring `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN=${TEST_RESET_TOKEN:?...}` via the overlay, AND adding the matching `killRs` / `startRs` / extended `resetState` Playwright helpers. **What this story MUST verify (no code change):**
- Running the existing `just default-config` (`docker compose --profile default config`) still succeeds and shows `resource-server` with `ENABLE_TEST_RESET=false` (or absent — pydantic-settings defaults to `False`).
- Running the existing `just e2e-config` (`docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config`) still succeeds (it does NOT include the RS in the e2e profile yet — that is Story 3.6's job — so the RS is silently absent from the e2e profile config output, which is the intentional pre-3.6 state).
- Capture both command outputs in the dev log to make the "deferred to 3.6" boundary explicit. Do NOT add `resource-server` to the e2e profile in this story; doing so would land Story 3.6's work prematurely without the matching Playwright helper updates and would risk a half-wired e2e stack.

[Source: epics.md#Story 3.4 lines 1302-1304 explicit defer note; `compose/app.yml` RS service `profiles: [default, dev]`; `compose/app.e2e.yml` BFF-only override; `Justfile` recipes `default-config` / `e2e-config`.]

**AC10 — Test coverage matrix.** Tests under `services/resource-server/tests/api/test_test_reset.py` (NEW file — name disambiguated from pytest's `test_*` convention by the doubled prefix; module is `tests/api/test_test_reset.py` so pytest discovers it and the RS route module is `src/resource_server/api/test_reset.py`) cover the scenarios enumerated in epic line 1311-1314, expanded to:

| # | Scenario | Setup | Asserted |
|---|---|---|---|
| 1 | Route not registered when `ENABLE_TEST_RESET=false` | build a fresh app with `enable_test_reset=False, test_reset_token="secret-xyz"` | `POST /v1/test/reset` → 404; response body matches FastAPI default `{"detail": "Not Found"}`; other methods (`GET`/`PUT`/`DELETE`) also return 404. NO WARN log emitted (gate off cleanly). |
| 2 | Route not registered when `ENABLE_TEST_RESET=true` but `TEST_RESET_TOKEN` is empty | `enable_test_reset=True, test_reset_token=""` | Same as #1 — 404 on all methods. WARN log `test_reset_route_skipped reason=test_reset_token_empty` captured via `caplog`. |
| 3 | Route not registered when `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN=" "` (whitespace only) | `enable_test_reset=True, test_reset_token="   "` | Same as #1 — 404. WARN log `test_reset_route_skipped reason=test_reset_token_empty` (empty-after-strip is the same classifier as empty). |
| 4 | Route not registered when `ENABLE_TEST_RESET=true` and `TEST_RESET_TOKEN="change-me"` (placeholder) | `enable_test_reset=True, test_reset_token="change-me"` | Same as #1 — 404. WARN log `test_reset_route_skipped reason=test_reset_token_default_placeholder` captured. **This is the RS-specific defensive check** that the BFF Story 1.12 does NOT have. |
| 5 | Missing `Authorization` header | gate ON, token=`"secret-xyz"`; POST with no auth header | 401 `{"errorCode": "session_expired", "message": "Authentication required", "detail": null}`; WARN log `test_reset_unauthorized: missing_header`; no DB writes (assert `select(func.count()).select_from(ReadingSpeed)` unchanged) |
| 6 | Empty `Authorization` header (`Authorization: ""`) | same | 401 `session_expired`; classifier `missing_header` (treat empty-string same as absent) |
| 7 | Non-`Bearer` scheme | `Authorization: Basic dGVzdA==` | 401 `session_expired`; classifier `wrong_scheme` |
| 8 | Non-`Bearer` scheme — JWT | `Authorization: JWT abc.def.ghi` | 401 `session_expired`; classifier `wrong_scheme`. (Specifically pin JWT-scheme rejection because the RS's *other* endpoints DO accept Bearer JWTs — making it doubly important that the test_reset route doesn't accidentally accept a JWT-shaped token.) |
| 9 | `Bearer` with no token | `Authorization: Bearer ` or `Authorization: Bearer   ` | 401 `session_expired`; classifier `empty_token` |
| 10 | `Bearer` with wrong token | `Authorization: Bearer wrong-value` | 401 `session_expired`; classifier `token_mismatch`; bearer string NOT in caplog text (grep `caplog.text` for `"wrong-value"` → must not appear) |
| 11 | `Bearer` with token differing only by trailing whitespace | `Authorization: Bearer secret-xyz ` (trailing space) | 401 `session_expired` (trailing whitespace is part of the token by spec; constant-time compare against the raw env value rejects). Classifier `token_mismatch`. |
| 12 | `Bearer` with extra tokens (`Bearer foo bar`) | `Authorization: Bearer foo bar` | 401 `session_expired`; classifier `token_mismatch` (the scheme is correct; the token after-strip would be `"foo bar"` which does not match — assert this classifier exactly, do NOT classify as `wrong_scheme`) |
| 13 | Correct bearer, empty table | gate ON, no rows seeded; POST with `Bearer secret-xyz` | 204; empty body (`response.content == b""`); `content-length: 0`; row count pre/post both 0; INFO log `test_reset_truncated tables=reading_speeds reading_speeds_deleted=0` |
| 14 | Correct bearer, `reading_speeds` populated (1 row) | seed 1 row via `session.add(ReadingSpeed(sub="user-a", pages_per_hour=30))`; POST | 204; row count = 0 post; INFO log `... reading_speeds_deleted=1` |
| 15 | Correct bearer, `reading_speeds` populated (5 rows, distinct subs) | seed 5 rows with distinct `sub` values; POST | 204; row count = 0 post; INFO log `... reading_speeds_deleted=5` |
| 16 | Correct bearer, JWT also attached (ignored) | gate ON, bearer correct, ALSO attach a fake `X-User: ...` and a malformed JWT-shaped string in a custom header | 204 (the route does NOT consult JWT material at all); INFO log `test_reset_truncated`; no `oidc_bearer.JWT_validation_failed` log line emitted (the JWT path never runs on this route). |
| 17 | Idempotent successive calls | gate ON, bearer correct; seed 3 rows; POST twice in a row | first → 204 `reading_speeds_deleted=3`; second → 204 `reading_speeds_deleted=0`; both INFO logs emitted in order; row count = 0 throughout |
| 18 | Bearer token containing special characters | gate ON, token=`"!@#$%^&*():_+"`; POST with matching bearer | 204 (no parsing/quoting issues — compared as bytes byte-for-byte) |
| 19 | Bearer token with leading/trailing whitespace in env | `monkeypatch` `settings.test_reset_token` to `"  abc  "`; client POSTs `Authorization: Bearer abc` (no spaces) | 401 `token_mismatch` (env value is compared verbatim; no `.strip()` on either side at compare time — only at gate-evaluation time for "is it empty"). Pin this behavior: secrets are NOT silently stripped. **Cross-reference Story 1.12 dev log line 505 — same convention.** |
| 20 | OpenAPI schema reflects gate (ON) | gate ON; `GET /openapi.json` | `body["paths"]` includes `/v1/test/reset` with the POST operation |
| 21 | OpenAPI schema reflects gate (OFF) | gate OFF; `GET /openapi.json` | `body["paths"]` does NOT include `/v1/test/reset` |
| 22 | INFO log on startup when gate ON | startup hook (lifespan or include-time) emits `test_reset_route_registered` | caplog at INFO captures it once per app build |
| 23 | INFO log NOT emitted when gate OFF | startup with gate OFF | caplog does NOT contain `test_reset_route_registered` |
| 24 | DB session rollback on commit failure | force `session.commit()` to raise (e.g., mock the engine to disconnect mid-transaction) | response is 500 with `errorCode: "internal_error"` (FastAPI's default for uncaught exceptions falls through to the existing handler chain); NO partial state persists (SQLAlchemy auto-rollback on context exit). **This scenario validates that the handler does NOT swallow DB errors** — if `commit()` fails, the operator wants a real 500, not a misleading 204. |
| 25 | Cross-user isolation: truncate removes ALL users' rows, not just one | seed 3 rows with `sub` ∈ {"user-a", "user-b", "user-c"}; POST with bearer | 204; all three rows gone (this IS the intended semantic — the e2e test reset is global, not per-user; document this explicitly because it differs from the per-user-`sub` scoping that `/v1/reading-speed` enforces) |

Coverage of `services/resource-server/src/resource_server/api/test_reset.py` AND the new `register_test_reset_router` function is **≥90%** per the project gate `[tool.coverage.report] fail_under = 90` (`services/resource-server/pyproject.toml:80`-ish — verify line). The epic's explicit ask (epics line 1314) is ≥90% on `src/resource_server/api/test_reset.py` — the project-wide gate plus this AC's coverage table satisfies it. [Source: epics.md#Story 3.4 lines 1311-1314; `services/resource-server/pyproject.toml`.]

**Implementation note (AC10 — fixtures):** The existing `tests/conftest.py` (lines 75-111) provides `engine` (session-scoped, in-memory SQLite), `session` (function-scoped AsyncSession with drop+recreate teardown), and `client` (ASGI test client with `get_session` dep override pointing at the per-test session). **The current `client` fixture uses the global `app` singleton from `resource_server.main`** which was built once at import time with the conftest's env-stub values (`ENABLE_TEST_RESET` defaults to `False` because `os.environ["ENV_FILE"] = ""` strips file loading at conftest.py:12). That global `app` does NOT have the test_reset route registered. **For this story's tests, the gate state varies per test**, so the recommended pattern is a `_build_test_context(enable: bool, token: str) -> tuple[FastAPI, AsyncEngine, AsyncSessionmaker]` helper local to `tests/api/test_test_reset.py` that builds a fresh `FastAPI` app + a fresh in-memory SQLite engine per scenario (mirroring Story 1.12's `_build_context` pattern). For scenarios that DO need the global `app` (e.g., scenario 7 testing the existing JWT-Bearer-rejection path), use the conftest's `client` fixture and rely on the absence of the test_reset route on that app (gate-off baseline) — the test asserts 404 + WARN log.

**AC11 — Gates remain green.** No new runtime or dev dependencies. From `services/resource-server/`:
- `uv sync --frozen` → exit 0 (lock untouched).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean. **Type note:** the bare `delete(ReadingSpeed)` SQLAlchemy call may need `# ty: ignore[arg-type]` to satisfy `ty`; mirror Story 1.12's pattern. Add the comment ONLY if the type-checker complains.
- `uv run pytest --cov` → all prior tests (242 at story start per `sprint-status.yaml` last_updated line) + new test_reset tests pass; total coverage ≥ 90%.
- No Alembic changes needed (the `0001_init` migration from Story 3.3 already creates `reading_speeds`).

[Source: epics.md#Story 3.4 lines 1311-1314; `services/resource-server/pyproject.toml`; `services/resource-server/CLAUDE.md` (quality gate enumeration).]

**AC12 — Pre-existing repo state is preserved outside the new code paths.** Files outside the new code paths are bit-for-bit identical to their pre-story state. Specifically: `CLAUDE.md`, root `README.md`, root `.env.example`, root `.env`, `docker-compose.yml`, `compose/app.yml`, `compose/app.e2e.yml`, `compose/infra.yml`, `Justfile`, `keycloak/**`, `services/bff/**`, `spa/**`, `e2e/**`, and `services/resource-server/{Dockerfile,entrypoint.sh,.gitattributes,.env.example,pyproject.toml,uv.lock,alembic.ini,alembic/env.py,alembic/script.py.mako,alembic/versions/0001_init_init_reading_speeds.py,src/resource_server/aop/**,src/resource_server/api/health.py,src/resource_server/api/v1/__init__.py,src/resource_server/api/v2/**,src/resource_server/api/schemas/**,src/resource_server/api/reading_speed.py,src/resource_server/auth/**,src/resource_server/observability/**,src/resource_server/core/config.py,src/resource_server/core/database.py,src/resource_server/core/constants.py,src/resource_server/core/errors.py,src/resource_server/core/exceptions.py,src/resource_server/factories/**,src/resource_server/models/dto/**,src/resource_server/models/entities/__init__.py,src/resource_server/models/entities/reading_speed.py,src/resource_server/services/reading_speed_service.py,src/resource_server/services/v1/**,src/resource_server/services/v2/**,tests/auth/**,tests/aop/**,tests/observability/**,tests/core/**,tests/models/**,tests/services/**,tests/api/{__init__.py,test_cors.py,test_health.py,test_reading_speed.py},tests/conftest.py}` are untouched. **The only modifications**: (i) new file `src/resource_server/api/test_reset.py`; (ii) new file `tests/api/test_test_reset.py`; (iii) two-line edit in `src/resource_server/main.py` (import + call); (iv) the `_bmad-output/implementation-artifacts/sprint-status.yaml` status flip across the workflow.

## Tasks / Subtasks

- [x] **Task 1: Author `src/resource_server/api/test_reset.py`** (AC: #1, #3, #4, #5, #6, #7)
  - [ ] Create file `services/resource-server/src/resource_server/api/test_reset.py` with module docstring describing: purpose ("e2e profile test-reset endpoint"), gating (`ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` non-empty AND non-placeholder), safety ("registered conditionally; production builds omit the route entirely"), and source references (epics §Story 3.4, architecture §"POST /v1/test/reset (e2e profile only)").
  - [ ] Imports:
    ```python
    from __future__ import annotations

    import hmac
    import logging
    from typing import Annotated, Final

    from fastapi import APIRouter, Depends, FastAPI, Request, Response
    from fastapi.responses import JSONResponse
    from sqlalchemy import delete as _delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from resource_server.core.config import AppSettings, settings
    from resource_server.core.database import get_session
    from resource_server.core.errors import ErrorCode
    from resource_server.models.entities.reading_speed import ReadingSpeed
    ```
    **Note:** the import is from `resource_server.models.entities.reading_speed` (the concrete module) NOT `resource_server.models.entities` (which re-exports via `__all__`). Both work; the direct module import is slightly more defensive against future re-export reshuffling.
  - [ ] Module-level constants:
    ```python
    logger = logging.getLogger(__name__)
    router = APIRouter(prefix="/v1", tags=["Test Reset"])
    _TEST_RESET_PATH: Final[str] = "/v1/test/reset"
    _BEARER_PREFIX: Final[str] = "Bearer "
    _PLACEHOLDER_TOKEN: Final[str] = "change-me"
    ```
    Note: the router prefix is `/v1` and the route path is `/test/reset` so the full mount is `/v1/test/reset`. Alternative: include into the existing `v1_router` from `api/v1/__init__.py`. **Don't do that** — the conditional registration is cleanest with a fresh `APIRouter` that gets `include_router`-ed only when the gate fires (the existing `v1_router` is unconditionally registered in `main.py:68`, so including our router into it would mount the route unconditionally, defeating the gate).
  - [ ] Helper `def _settings_dep() -> AppSettings: return settings` (matches the test_reset_service pattern; lets the test suite override via `app.dependency_overrides[_settings_dep] = lambda: AppSettings(...)`).
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
    **Note:** does NOT use `AppException(ErrorCode.SESSION_EXPIRED)` + raise (which would route through `app_exception_handler` and produce the same envelope), because raising-and-handling here would obscure the WARN-log emission point and mix the route's bespoke auth model with the JWT auth model. Returning a `JSONResponse` directly keeps the auth control flow local and explicit.
  - [ ] Helper `def _classify_auth_failure(auth_header: str | None) -> str | None`:
    - Returns `None` if the header parses to a non-empty bearer token (caller then validates the value).
    - Returns one of `"missing_header"` / `"wrong_scheme"` / `"empty_token"` otherwise.
    - Logic:
      - If `auth_header is None` or `auth_header.strip() == ""` → `"missing_header"`.
      - If `not auth_header.startswith(_BEARER_PREFIX)` (case-sensitive — RFC 6750 §2.1 makes the scheme case-insensitive but the project's convention is to match exactly per BFF Story 1.12; document as an accepted simplification) → `"wrong_scheme"`.
      - Strip the prefix → `token = auth_header[len(_BEARER_PREFIX):]`. If `token.strip() == ""` → `"empty_token"`.
      - Else return `None` (token format is valid; caller compares it).
    - **Do NOT classify "Bearer foo bar" as `wrong_scheme`** — the scheme is correct (`Bearer`); the post-prefix content `"foo bar"` is a bearer-token-shaped string that simply doesn't match the env value. Classify as `token_mismatch` at the caller's comparison step (scenario 12 enforces this).
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
        # auth_header is guaranteed to start with "Bearer " here per _classify_auth_failure
        assert auth_header is not None  # ty narrowing
        provided = auth_header[len(_BEARER_PREFIX):]
        expected = cfg.test_reset_token
        if not hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8")):
            logger.warning("test_reset_unauthorized: token_mismatch")
            return _unauthorized_response()

        # Happy path: truncate reading_speeds; single commit
        result = await db.execute(
            _delete(ReadingSpeed),
            execution_options={"synchronize_session": False},
        )
        await db.commit()
        deleted = getattr(result, "rowcount", -1)
        logger.info(
            "test_reset_truncated tables=reading_speeds reading_speeds_deleted=%s",
            deleted,
        )
        return Response(status_code=204)
    ```
    **Type note:** the `_delete(ReadingSpeed)` call may need `# ty: ignore[arg-type]` to satisfy `ty`. Confirm by running `uv run ty check` and add the comment only if the type-checker complains. The `assert auth_header is not None` after the classification branch is a `ty`-narrowing hint; ruff will complain about bare `assert` in production code only if `assert` is on the lint deny-list (it isn't in this project's `[tool.ruff.lint.select]` — see `pyproject.toml`).
  - [ ] Helper `def register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None`:
    ```python
    if not cfg.enable_test_reset:
        return
    stripped = cfg.test_reset_token.strip()
    if not stripped:
        # Defense-in-depth: empty / whitespace-only token == "not configured"
        logger.warning(
            "test_reset_route_skipped reason=test_reset_token_empty"
        )
        return
    if stripped == _PLACEHOLDER_TOKEN:
        # Defense-in-depth: archetype default in .env.example is "change-me";
        # a real production stack must rotate this before enabling the gate.
        logger.warning(
            "test_reset_route_skipped reason=test_reset_token_default_placeholder"
        )
        return
    app.include_router(router)
    logger.info("test_reset_route_registered path=%s", _TEST_RESET_PATH)
    ```
  - [ ] Module-level `__all__ = ["router", "register_test_reset_router"]` so the imports from `main.py` are explicit.

- [x] **Task 2: Wire the registration helper into `main.py`** (AC: #1, #3)
  - [ ] In `services/resource-server/src/resource_server/main.py`, add the import after the existing `from resource_server.api.v2 import router as v2_router` line (currently `main.py:11`):
    ```python
    from resource_server.api.test_reset import register_test_reset_router
    ```
  - [ ] AFTER `app.include_router(v2_router)` (currently `main.py:69`), add a SINGLE call:
    ```python
    register_test_reset_router(app, settings)
    ```
  - [ ] **Important ordering note:** the call MUST come AFTER `add_exception_handler` calls (currently `main.py:65-66`) so that the new route — if registered — is wrapped by the existing exception handlers (relevant for scenario 24 where a `commit()` failure surfaces via the chain). FastAPI's middleware/handler/router stack is built lazily on first request, so route registration after `add_exception_handler` is functionally fine; placing it right after the existing `include_router` calls is the most readable choice.
  - [ ] **DO NOT** modify `services/resource-server/src/resource_server/api/v1/__init__.py`. The test-reset router is mounted into `app` directly via `register_test_reset_router`, NOT included into `v1_router`. Reason: `v1_router` is unconditionally mounted at `main.py:68`; including our test-reset router into `v1_router` would defeat the gate.

- [x] **Task 3: Author tests `tests/api/test_test_reset.py`** (AC: #2, #4–#7, #10 scenarios 1–25)
  - [ ] Create `services/resource-server/tests/api/test_test_reset.py`. Module docstring: "Route-level tests for POST /v1/test/reset (Story 3.4). Covers gating (env on/off + placeholder rejection), bearer auth, truncation of `reading_speeds`, JWT-non-interaction, and OpenAPI surface."
  - [ ] Imports:
    ```python
    from __future__ import annotations

    import logging
    from collections.abc import AsyncGenerator
    from typing import Final

    import pytest
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel

    from resource_server.api.test_reset import register_test_reset_router
    from resource_server.core.config import AppSettings
    from resource_server.core.database import get_session
    from resource_server.core.errors import (
        AppException,
        app_exception_handler,
        validation_exception_handler,
    )
    from resource_server.models.entities.reading_speed import ReadingSpeed
    ```
  - [ ] Helper `async def _build_test_context(enable: bool, token: str) -> tuple[FastAPI, AsyncEngine, async_sessionmaker[AsyncSession]]`:
    - Builds a fresh `AppSettings` via the existing constructor with kwargs `enable_test_reset=enable, test_reset_token=token`. Note: `AppSettings` has required-fail-fast for `OIDC_ISSUER_URL` / `OIDC_JWKS_URL` / `OIDC_AUDIENCE` — pass placeholder values matching the conftest stubs (lines 20-25): `oidc_issuer_url="http://keycloak-test/realms/test"`, `oidc_jwks_url="http://keycloak-test/realms/test/protocol/openid-connect/certs"`, `oidc_audience="bmad-books-resource-server"`.
    - Creates a fresh in-memory SQLite engine via the same pattern as conftest.py:75-87 (`create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)`) and runs `SQLModel.metadata.create_all`.
    - Builds a fresh `FastAPI()` instance — does NOT use the global `resource_server.main:app`. Adds the existing `app_exception_handler` for `AppException` and `validation_exception_handler` for `RequestValidationError` so the response envelopes match production (mirrors `main.py:65-66`).
    - Overrides `get_session` to yield from the fresh engine's sessionmaker.
    - Calls `register_test_reset_router(app, cfg)` with the constructed settings.
    - Returns `(app, engine, sessionmaker)` so tests can seed rows + assert.
  - [ ] **Fixture for caplog level:** at module top, set `pytest.fixture(autouse=True)` that sets `caplog.set_level(logging.WARNING, logger="resource_server.api.test_reset")` OR use `caplog.set_level(...)` per-test. The latter is preferred for clarity — caplog by default captures WARNING+; INFO assertions (scenarios 13–17, 22) MUST explicitly call `caplog.set_level(logging.INFO, logger="resource_server.api.test_reset")`.
  - [ ] **Implement scenarios 1–4 (route not registered):**
    - Each test calls `_build_test_context(enable, token)` with the variant, then `async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c: response = await c.post("/v1/test/reset")`. Asserts `response.status_code == 404` and `response.json() == {"detail": "Not Found"}`.
    - Scenarios 2, 3, 4 also assert the WARN log from `register_test_reset_router` is present with the appropriate classifier (`test_reset_route_skipped reason=test_reset_token_empty` for 2 + 3; `test_reset_route_skipped reason=test_reset_token_default_placeholder` for 4). Scenario 1 asserts the WARN log is NOT present (clean gate-off).
    - Also assert other methods return 404: `for method in ["get", "put", "delete", "patch"]: response = await c.request(method.upper(), "/v1/test/reset"); assert response.status_code == 404`.
  - [ ] **Implement scenarios 5–12 (auth failure modes):**
    - Use `_build_test_context(enable=True, token="secret-xyz")`. Seed ZERO rows. POST `/v1/test/reset` with the variant Authorization header. Assert 401 + envelope shape + WARN classifier + zero DB writes (assert `select(func.count()).select_from(ReadingSpeed)` returns 0 before and after the request).
    - Scenario 7 (Basic scheme) and 8 (JWT scheme) BOTH classify as `wrong_scheme`. Pin scenario 8 separately because of the RS's JWT-acceptance on `/v1/reading-speed` — a regression where the test_reset route inadvertently picks up `oidc_bearer.get_authenticated_principal` would silently 401 with a different log line; scenario 8 fails on log-line shape if that ever happens.
    - Scenario 10 (`Bearer wrong-value`) — assert `caplog.text` does NOT contain the string `"wrong-value"` (the bearer should never appear in logs).
    - Scenario 12 (`Bearer foo bar`) — assert classifier is exactly `token_mismatch`, NOT `wrong_scheme`.
  - [ ] **Implement scenarios 13–15 (happy path + row count assertions):**
    - Use the per-test app + sessionmaker. Seed 0 / 1 / 5 rows directly via `async with sessionmaker() as session: session.add_all([ReadingSpeed(sub="user-N", pages_per_hour=30+N) for N in range(K)]); await session.commit()`. POST with `Authorization: Bearer secret-xyz`. Assert 204 + `response.content == b""` + `response.headers.get("content-length") == "0"`.
    - Re-query and assert `(await session.execute(select(func.count()).select_from(ReadingSpeed))).scalar_one() == 0`.
    - Capture caplog at INFO and assert the `test_reset_truncated tables=reading_speeds reading_speeds_deleted=<K>` line with the exact `<K>`.
    - **Critical:** the test MUST use the SAME session/engine that the test app's `get_session` dependency yields. The `_build_test_context` helper centralizes this by returning the sessionmaker — use it for BOTH seeding AND post-asserting.
  - [ ] **Implement scenario 16 (JWT non-interaction):**
    - POST with `Authorization: Bearer secret-xyz` AND custom headers `X-User: "attacker"` and `X-Forwarded-Token: "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhdHRhY2tlciJ9.invalid"`. Assert 204 (the route ignores everything except the configured bearer).
    - Capture caplog and assert NO log line from the `resource_server.auth.oidc_bearer` logger is present (the JWT validation path never ran).
  - [ ] **Implement scenario 17 (idempotency):**
    - Seed 3 rows. POST twice in a row. First → 204 + `reading_speeds_deleted=3` log; second → 204 + `reading_speeds_deleted=0` log. Both INFO logs captured in order via `caplog.records`.
  - [ ] **Implement scenarios 18–19 (edge cases):**
    - Scenario 18: `_build_test_context(enable=True, token="!@#$%^&*():_+")`. POST with matching bearer. Assert 204.
    - Scenario 19: `_build_test_context(enable=True, token="  abc  ")`. POST `Authorization: Bearer abc` (no spaces). Assert 401 + `token_mismatch` (verbatim compare; env value is NOT silently stripped at comparison time even though it IS stripped at gate-evaluation time for "is it empty / placeholder").
  - [ ] **Implement scenarios 20–23 (OpenAPI + startup logs):**
    - Scenario 20: gate ON → `GET /openapi.json` → `"/v1/test/reset"` in `body["paths"]`, with the `post` operation present (`body["paths"]["/v1/test/reset"]["post"]["tags"] == ["Test Reset"]`).
    - Scenario 21: gate OFF → `"/v1/test/reset"` NOT in paths.
    - Scenario 22: capture caplog at INFO during `_build_test_context(enable=True, token="secret-xyz")` → caplog contains `test_reset_route_registered path=/v1/test/reset`.
    - Scenario 23: capture caplog during `_build_test_context(enable=False, token="secret-xyz")` → caplog does NOT contain `test_reset_route_registered`.
  - [ ] **Implement scenario 24 (commit failure):**
    - Build a context. Seed 1 row. Monkeypatch the session-override to yield a session whose `commit()` raises `RuntimeError("simulated DB disconnect")` once. POST. Assert response status is 500 with body `{"errorCode": "INTERNAL_ERROR", ...}` (the FastAPI default exception → 500 INTERNAL_ERROR via the conftest-installed exception handlers — verify by reading `core/errors.py` to confirm the 500 envelope shape; if the RS does NOT install a custom `Exception` handler today (it doesn't — only `AppException` and `RequestValidationError`), the response will be FastAPI's default 500 with body `Internal Server Error` and `Content-Type: text/plain`). Pin whatever the actual behavior is and document it; the goal is to **prove the handler does not swallow the error**, not to assert a specific envelope shape.
    - Re-query: row still exists (rollback fired on session-context exit per SQLAlchemy semantics).
  - [ ] **Implement scenario 25 (cross-user isolation — truncate is global):**
    - Seed rows for `sub` ∈ {"user-a", "user-b", "user-c"}. POST with bearer. Assert all 3 are deleted (not just one). Document in the test docstring: "truncate is intentionally global; this differs from `/v1/reading-speed` GET/PUT which are sub-scoped — the test_reset endpoint is the e2e clean-slate primitive, not a per-user clear."
  - [ ] Run `uv run pytest tests/api/test_test_reset.py -v --cov=src/resource_server/api/test_reset` → all 25+ new tests pass; coverage of `test_reset.py` ≥ 90%.

- [x] **Task 4: Verify no compose changes are needed (AC8 + AC9)**
  - [ ] From repo root: `docker compose --profile default config` → valid; the rendered `resource-server` service has NO `ENABLE_TEST_RESET=true` (it should have NO `environment:` block for `ENABLE_TEST_RESET` at all on the `default` profile — the env_file points at the per-service `.env`, which keeps it as the default `false`). Capture output excerpt in dev log.
  - [ ] From repo root: `just e2e-config` (which is `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config`) → valid; the rendered `bff` service has `ENABLE_TEST_RESET=true` (from the existing BFF overlay) but `resource-server` is NOT listed in the e2e profile output (because the base `resource-server` service still has `profiles: [default, dev]` — Story 3.6 will add `e2e` to that list). Capture output excerpt in dev log to make the "deferred to 3.6" boundary explicit.
  - [ ] **Do NOT** modify `compose/app.yml` (`resource-server` profiles list) or `compose/app.e2e.yml` (add an RS overlay) in this story. Both belong to Story 3.6.
  - [ ] `docker compose build resource-server` → succeeds (no Dockerfile changes; image still builds).

- [x] **Task 5: Run the full RS gate matrix** (AC: #11)
  - [ ] From `services/resource-server/`:
    - `uv sync --frozen` → exit 0 (no dep changes).
    - `uv run ruff check` → clean.
    - `uv run ruff format --check` → clean.
    - `uv run ty check` → clean. Add `# ty: ignore[...]` comments ONLY if the type-checker objects to the bare `_delete(ReadingSpeed)` SQLAlchemy call — Story 3.3 dev log notes the RS's ty configuration is strict; mirror the BFF Story 1.12 pattern if needed.
    - `uv run pytest --cov` → all 242 prior tests + 25+ new test_reset tests pass; total coverage ≥ 90%. Capture the post-change %.
  - [ ] No Alembic migration needed (the `reading_speeds` table already exists from Story 3.3).
  - [ ] Capture command output excerpts in **Debug Log References**.

- [x] **Task 6: Update sprint-status + deferred-work**
  - [ ] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `3-4-rs-post-v1-test-reset-endpoint: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [ ] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [ ] If any new defects surface during implementation, append them as D71+ in `deferred-work.md` with severity / owner-story / rationale (mirrors the discipline established by Stories 3.1, 3.2, 3.3).
  - [ ] The Story 1.12-style "BFF could adopt the `change-me` placeholder reject too" observation is itself a deferred item — log it as D71 in `deferred-work.md` with severity `nit (defense-in-depth parity)` and owner-story `5.2 (security review document)`. **Do NOT modify the BFF in this story.**

## Dev Notes

### What this story is — and is not

**This story implements the RS's hidden test-reset endpoint: `POST /v1/test/reset`. Behind a three-key gate (`ENABLE_TEST_RESET=true` AND `TEST_RESET_TOKEN` non-empty AND `TEST_RESET_TOKEN != "change-me"`), it accepts a bearer token, truncates the `reading_speeds` table, and returns 204. When the gate is off (default), the route is not registered and any request gets FastAPI's standard 404 (`{"detail": "Not Found"}`). Production builds (the `default` compose profile) leave the gate off.**

**Explicitly NOT in scope (each is a downstream story OR not part of this story's contract):**

- **No compose changes.** Story 3.6 owns adding `resource-server` to the `e2e` profile AND wiring `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` via the overlay (epics §Story 3.4 line 1302-1304 explicit defer). Do NOT preempt 3.6's work — adding the RS to e2e here without the matching `killRs` / `startRs` / `resetState` Playwright helper updates would land a half-wired e2e stack.
- **No BFF changes.** This is a pure RS story. Story 1.12 already shipped the BFF's `POST /v1/test/reset`; the two endpoints share NO code (per Story 1.12 Dev Notes line 356 — "RS will have its own gating + bearer-check; this story's `test_reset.py` is BFF-only").
- **No SPA changes.** This is a pure backend story. The Playwright fixtures (Story 1.11) call the BFF endpoint today; Story 3.6 extends the `resetState` helper to ALSO call the RS endpoint.
- **No Playwright spec authored.** Story 3.6 is the first consumer of this endpoint inside a real test (J4 spec for "adjust reading speed").
- **No Keycloak truncation.** The endpoint touches the RS-owned `reading_speeds` table only.
- **No CSRF middleware exemption.** The RS doesn't have a CSRF middleware (it's stateless OAuth-resource-server). Contrast Story 1.12's `services/bff/src/bff/auth/csrf.py` change — RS has nothing analogous.
- **No `oidc_bearer` JWT plumbing on the route.** The test_reset route uses ONLY the env-bearer; it does NOT accept JWT tokens (scenario 16 enforces non-interaction).
- **No new ErrorCode added.** Reuses the existing `ErrorCode.SESSION_EXPIRED` (401) for all auth-failure modes — same as the BFF Story 1.12 (no `INVALID_TEST_RESET_BEARER` enum member; adding one would leak that the endpoint exists to attackers via errorCode differing from a vanilla `/v1/<unknown>` 404).
- **No rate limiting on the endpoint.** Out of scope; trusted bearer auth + path-only exposure + gate-off-in-production is the protection model.
- **No production-time defense beyond gate-off + placeholder-reject.** If an operator misconfigures production with `ENABLE_TEST_RESET=true` AND a real (non-placeholder) `TEST_RESET_TOKEN` AND leaks the token, the route is exploitable. This is documented in PRD §4 "out of scope".

### Dependencies (CRITICAL — read before starting)

**Story 3.1 (`done`)** — owns the RS scaffold, `core/errors.py:9-46` with `ErrorCode.SESSION_EXPIRED` (401) already wired, `app_exception_handler` registered in `main.py:65`, `AppSettings` declares `enable_test_reset: bool = False` and `test_reset_token: str = "change-me"` (config.py:93-94), `.env.example` ships the two env-var entries (lines 58-59). **No re-declaration needed — these are load-bearing for this story's gate logic.**

**Story 3.2 (`done`)** — owns `oidc_bearer` plugin and the per-route `Depends(require_scope(...))` model. **This story explicitly does NOT use `Depends(require_scope(...))` on the test_reset route** — that's the whole point of the env-bearer auth. The contrast matters: if a future maintainer adds `Depends(get_authenticated_principal)` to the test_reset handler "for safety", they would BREAK the gate (the route would require a JWT in addition to the env-bearer, making the e2e fixture's bearer-only call 401).

**Story 3.3 (`done`)** — owns the `ReadingSpeed` SQLModel + `0001_init` Alembic migration. **This story TRUNCATES `reading_speeds`** — no schema changes. The `ReadingSpeed` model is imported from `resource_server.models.entities.reading_speed` (direct module import, NOT via `resource_server.models.entities.__all__`).

**Story 3.5 (`backlog`)** — adds the BFF's `ResourceServerClient` that proxies `/v1/reading-speed` to the RS. **This story is upstream of 3.5** — 3.5 does NOT consume this endpoint (the BFF proxies USER traffic via the JWT-validated `/v1/reading-speed`, not via the test-reset bearer).

**Story 3.6 (`backlog`)** — the FIRST consumer of this endpoint from the test side. Owns: (a) adding `resource-server` to the `e2e` compose profile in `compose/app.yml`, (b) extending `compose/app.e2e.yml` to add an RS env override OR adding a new `compose/app.e2e-rs.yml` overlay, (c) extending the Playwright `resetState(...)` fixture to ALSO call the RS endpoint, (d) implementing `killRs` / `startRs` helpers for the J6 honest-failure spec, (e) the J4 Playwright spec. **This story MUST land before 3.6 starts** (Story 3.6 has nothing to call without it).

**Story 1.12 (`done`)** — the BFF analog. Implementation reference. **Copy the gating + bearer-check pattern from the BFF; do NOT share code (there is no cross-service shared module per architecture §I3).**

**Story 4.1 (`backlog`)** — adds the RS's `POST /v1/estimate` endpoint. **This story is upstream of 4.1** — 4.1's tests will rely on a clean `reading_speeds` slate for some scenarios; the test-reset endpoint is what gives them that.

**Story 2.3 (`backlog`)** — extends the BFF's `test_reset.py` to truncate `books`. **NOT relevant to this story** — `books` is a BFF table; the RS has no `books` table.

### Architecture compliance

- **AR32 (epics line 97)** — "Test reset endpoint: `POST /v1/test/reset` on BFF (truncates `books`, `sessions`, `auth_states`) and RS (truncates `reading_speeds`). Available only when `ENABLE_TEST_RESET=true`; requires shared bearer from `TEST_RESET_TOKEN`. Returns 204. Production builds do not register the route." — this story implements the **RS half**. The BFF half landed in Story 1.12.
- **Architecture §"POST /v1/test/reset (e2e profile only)" lines 1354-1360** — wire contract: 204 success, 404 when off, bearer required, gated by `ENABLE_TEST_RESET`. Symmetric with the BFF.
- **Architecture §C5 line 396 (ErrorCode enum)** — `session_expired` is the 401 code already used by the RS's `oidc_bearer.get_authenticated_principal` (`auth/oidc_bearer.py:122-127`); this story REUSES it for the missing/wrong bearer case (no new `ErrorCode` member needed — there is no `INVALID_TEST_RESET_BEARER` enum member, and adding one would leak that the endpoint exists to attackers via the errorCode differing from a vanilla `/v1/<unknown>` 404).
- **Architecture §C6** — timeouts: no external HTTP calls in this handler, so timeouts/retries don't apply. The handler only touches the local DB.
- **Architecture §"Logging conventions" lines 781-788** — never log token material; truncate ids to first-8-chars in INFO logs. This handler logs ZERO ids (truncate is a table-wide operation; no per-row context) and ZERO token material. Classifier strings are the only auth-failure context logged.
- **Source-tree (architecture §line 972)** — `src/resource_server/api/test_reset.py` is the canonical location for the RS module; `tests/api/test_test_reset.py` is the canonical test location (the doubled `test_test_` prefix is intentional — `test_reset.py` is the production module name, not a test file).
- **Architecture §C7 (DTO boundary)** — does NOT apply: the test-reset endpoint has NO request body and NO response body (it's 204), so there is no DTO surface to author.
- **CLAUDE.md (RS-level)** — "Agents SHALL strictly adhere to documented technical specifications. Agents MUST limit themselves to the adoption of the technologies and libraries listed in the documentation." This story adds NO new dependencies. All imports are already in `pyproject.toml` from Stories 3.1–3.3.

### Library / framework requirements

No new dependencies. All imports are already in the RS's `pyproject.toml`:
- `fastapi` (already pinned ≥0.135.1 — provides `APIRouter`, `FastAPI`, `Request`, `Response`, `Depends`, `JSONResponse`).
- `sqlalchemy` / `sqlmodel` (already pinned — provides `delete`, `AsyncSession`).
- `hmac` (stdlib — used for constant-time bearer compare).
- `logging` (stdlib).
- No new runtime deps; no new dev deps.

Python 3.14 is the project floor (`services/resource-server/pyproject.toml:9` `requires-python = ">=3.14"`). Match the existing codebase's style: type annotations everywhere, `Annotated[...]` for `Depends`, `from __future__ import annotations` IS used in this codebase (verified at `core/exceptions.py`, `api/reading_speed.py`, `services/reading_speed_service.py`) — include it at the top of `test_reset.py` for consistency.

### File structure requirements

**New files:**
- `services/resource-server/src/resource_server/api/test_reset.py` — the route module + `register_test_reset_router` helper + `_classify_auth_failure` + `_unauthorized_response` helpers + `_settings_dep` factory. Module docstring describes purpose, gating, auth, safety, and source references.
- `services/resource-server/tests/api/test_test_reset.py` — pytest module covering all 25 AC10 scenarios. Doubled `test_` prefix is intentional (pytest discovers it; the RS route module is `test_reset.py` without the prefix). Helper `_build_test_context(enable, token)` builds a fresh `FastAPI` app + in-memory SQLite engine per test for full isolation.

**Modified files:**
- `services/resource-server/src/resource_server/main.py` — added `from resource_server.api.test_reset import register_test_reset_router` import and a single `register_test_reset_router(app, settings)` call after `app.include_router(v2_router)` (currently `main.py:69`). Two-line diff.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip `3-4-rs-post-v1-test-reset-endpoint` status across the workflow (`ready-for-dev` → `in-progress` → `review` → `done` by code-review).
- `_bmad-output/implementation-artifacts/deferred-work.md` — append D71 ("BFF could adopt `change-me` placeholder reject for parity") with severity nit, owner-story 5.2.

**NOT modified:**
- `services/resource-server/src/resource_server/core/config.py` — `enable_test_reset` (line 93) and `test_reset_token` (line 94) are ALREADY declared.
- `services/resource-server/.env.example` — `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` are ALREADY present (lines 58-59).
- `services/resource-server/src/resource_server/api/v1/__init__.py` — the test-reset router is mounted into `app` directly via the helper, NOT included into `v1_router`.
- `services/resource-server/src/resource_server/services/reading_speed_service.py` — no truncate method added; the truncate is handler-local in `api/test_reset.py`.
- `services/resource-server/src/resource_server/models/entities/reading_speed.py` — schema unchanged from Story 3.3.
- Alembic migrations — no schema changes; the `0001_init` from Story 3.3 already creates `reading_speeds`.
- `services/resource-server/pyproject.toml` — no new dependencies.
- `compose/app.yml` / `compose/app.e2e.yml` / `Justfile` — all deferred to Story 3.6 per epic line 1302-1304.

### Testing standards

- **Framework:** pytest 8+, pytest-asyncio (already pinned per `services/resource-server/pyproject.toml`).
- **HTTP client:** `httpx.AsyncClient(transport=ASGITransport(app=app))` — matches conftest pattern (conftest.py:107-110).
- **DB:** in-memory SQLite via `create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)` — matches conftest pattern (conftest.py:75-87).
- **Log assertion:** use pytest's `caplog` fixture; assert on `caplog.records` (preferred — gives access to `levelname` + `message`) or `caplog.text`. Explicitly call `caplog.set_level(logging.INFO, logger="resource_server.api.test_reset")` for INFO assertions (caplog defaults to WARNING).
- **Coverage gate:** total project `fail_under = 90` (`services/resource-server/pyproject.toml`). Per-module ≥90% for `src/resource_server/api/test_reset.py` per epic line 1314.
- **Test naming:** the test file is `tests/api/test_test_reset.py` so pytest discovers it. Inside, prefer top-level `async def test_<scenario>(...)` functions matching the style of `tests/api/test_reading_speed.py` — no `class TestX` wrappers unless they add clarity for a sub-group.
- **Lint/format:** `uv run ruff check` and `uv run ruff format --check` must be clean. `uv run ty check` must be clean (both errors and warnings — per `services/resource-server/CLAUDE.md` "do not add blanket suppressions unless justified and documented").
- **Python invocation:** all commands in this story (and any inline scripting in tests) use `python` (not `python3`) per the project convention (root `CLAUDE.md`). The Dockerfile and compose healthchecks already use `python` — no changes needed there.

### Previous story intelligence

**From Story 1.12 (BFF analog — `done`):**
- The doubled-prefix test file name (`test_test_reset.py`) is the load-bearing pytest-discovery pattern; do NOT collapse to `test_reset.py` (which would collide with the production module name's package-relative reference).
- `Response(status_code=204)` (NOT `JSONResponse(status_code=204, content=None)`) — emits an empty body with `content-length: 0`. Pin scenario 13's empty-body assertion to `response.content == b""` AND `response.headers.get("content-length") == "0"` (Story 1.12 dev log line 504 confirms this).
- `hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))` is the correct primitive for constant-time bearer compare (Story 1.12 dev log line 503-504).
- Test fixtures should build a FRESH `FastAPI` app per gate-state variant rather than monkeypatching the global `app` (which can't be un-`include_router`-ed cleanly between tests). Story 1.12 dev log line 502 documents this decision — same pattern here.
- Story 1.12 chose `Option B (overlay file)` for compose (Story 1.12 dev log line 504). The RS story DEFERS compose work entirely to 3.6 — but when 3.6 writes its overlay, it should mirror 1.12's overlay shape (`compose/app.e2e-rs.yml` is the natural name; alternatively, extend `compose/app.e2e.yml` to overlay both services).

**From Story 3.3 (RS `ReadingSpeed` model — `done`):**
- `ReadingSpeed` is in `resource_server.models.entities.reading_speed`; the `__all__ = ["ReadingSpeed"]` in `entities/__init__.py` exports it. Direct module import is preferred for `test_reset.py` (Story 3.3 dev log line 506 — defensive against future re-export reshuffling).
- The `core/exceptions.py` pattern (subclass `AppException` with a fixed `ErrorCode`) is the right way to do domain exceptions. **This story does NOT need a new exception** because all auth failures emit `SESSION_EXPIRED` via a direct `JSONResponse` (the auth flow is bespoke, not a domain exception).
- `validation_exception_handler` already strips the `input` field from Pydantic errors (`core/errors.py:81-89`). **This story's route does NOT take a request body**, so `RequestValidationError` is unreachable — no validation-handler concerns.
- The `effective_database_url` property in `AppSettings` resolves `RS_DATABASE_URL` → `DATABASE_URL` → `sqlite://` (`core/config.py:188-198`). Tests build a fresh engine directly via `create_async_engine(...)` and do NOT consult this property — same as Story 3.3's tests.

**From Story 3.2 (RS `oidc_bearer` — `done`):**
- The `oidc_bearer.get_authenticated_principal` is a per-route `Depends`, not middleware. **This story's route handler MUST NOT take a `Principal` parameter** — that would chain it into the JWT-validation path and break the bearer-only auth model.
- `require_scope(scope)` is the scope-gating factory. **This story does NOT call it.**
- The synthetic-IdP harness (`tests/auth/synthetic_idp.py`) is NOT relevant — this story's tests don't mint JWTs because the test-reset route doesn't validate JWTs.

**From Story 3.1 (RS scaffold — `done`):**
- `AppSettings` has required-fail-fast for `OIDC_ISSUER_URL` / `OIDC_JWKS_URL` / `OIDC_AUDIENCE` (`core/config.py:114-139`). When building `AppSettings(**kwargs)` in tests, pass non-empty placeholders or pytest will reject construction.
- `core/errors.py:9-51` defines `ErrorCode` (enum) and `AppException` (base class). `ErrorCode.SESSION_EXPIRED` and `ErrorCode.INVALID_INPUT` already exist with the right HTTP statuses.
- The `app_exception_handler` is at `core/errors.py:67-74`; the `validation_exception_handler` is at `core/errors.py:77-97`. Both are registered in `main.py:65-66`. Tests that build a fresh `FastAPI` must register BOTH handlers (mirrored at `_build_test_context` task above).

### Review Findings

- [x] [Review][Patch] CR1 [Med] Startup-time WARN missing when `TEST_RESET_TOKEN` has surrounding whitespace [services/resource-server/src/resource_server/api/test_reset.py:181-194] — registration uses `cfg.test_reset_token.strip()` for the gate while the handler runtime compare uses the raw `cfg.test_reset_token`. Operator sets `TEST_RESET_TOKEN="\nsecret\n"` → route IS registered (strip non-empty + not placeholder) but every legitimate `Bearer secret` request silently 401s with `token_mismatch`. Fix: when `stripped != cfg.test_reset_token`, emit a startup WARN log `test_reset_token_whitespace_padded` so operators see the misconfig at boot instead of debugging 401s. Found by: Blind + Edge.
- [x] [Review][Patch] CR2 [Med] OpenAPI surface declares only 204; 401 envelope not documented [services/resource-server/src/resource_server/api/test_reset.py:124] — `@router.post("/test/reset", status_code=204)` declares only the 204 path; the handler also returns a 401 `JSONResponse` for every auth-failure mode but the OpenAPI schema generated for this route lists no `401` response. SDK generators consuming `/openapi.json` treat the 401 as an unspecified surprise. Fix: add `responses={401: {"description": "Authentication required (env-bearer)", "content": {"application/json": {"example": {"errorCode": "session_expired", "message": "Authentication required", "detail": None}}}}}` to the decorator. Found by: Blind + Edge.
- [x] [Review][Patch] CR3 [Med] Placeholder reject is case-sensitive and bypassed by trivial casing/typo [services/resource-server/src/resource_server/api/test_reset.py:62, 188-192] — `stripped == _PLACEHOLDER_TOKEN` only matches the exact string `"change-me"`. `Change-Me`, `CHANGE-ME`, `change_me`, `changeme` all bypass the defense-in-depth check while still being recognizably derived from the public template default. Fix: normalize before compare — `stripped.lower().replace("_", "-")` and expand `_PLACEHOLDER_TOKENS: Final[frozenset[str]] = frozenset({"change-me", "changeme"})`. Add scenarios covering `Change-Me` and `CHANGE-ME` to ensure the reject fires. Found by: Blind + Edge.
- [x] [Review][Defer] D74 [Med] `_classify_auth_failure` does not detect multi-bearer concat per RFC 9110 §5.3 [services/resource-server/src/resource_server/api/test_reset.py:127-132] — deferred to Story 5.2 (security review document); cross-service issue (BFF has same pattern).
- [x] [Review][Defer] D75 [Med] Module-level `router` exposed via `__all__` enables gate bypass [services/resource-server/src/resource_server/api/test_reset.py:69,76] — deferred; cross-service hardening pass needed (BFF Story 1.12 has the same export shape; coordinated fix belongs to Story 5.2).
- [x] [Review][Defer] D76 [Low] `assert auth_header is not None` could be stripped under `PYTHONOPTIMIZE=1` [services/resource-server/src/resource_server/api/test_reset.py:138] — deferred to a code-quality cleanup pass (`PYTHONOPTIMIZE` is not used in any project Dockerfile / CI invocation today).
- [x] [Review][Defer] D77 [Low] `# type: ignore[arg-type]` on `**_OIDC_STUBS` hides typo signal [services/resource-server/tests/api/test_test_reset.py:84] — deferred to test-quality cleanup pass (typed-dict refactor of `_OIDC_STUBS`).
- [x] [Review][Defer] D78 [Low] `register_test_reset_router` not idempotent (double-call mounts route twice) [services/resource-server/src/resource_server/api/test_reset.py:181-194] — deferred to defensive-coding pass (no current call site invokes it more than once per app instance).
- [x] [Review][Defer] D79 [Low] Non-`AppException` exceptions (e.g., DB driver `OperationalError`) bypass the project envelope and surface as default 500 [services/resource-server/src/resource_server/api/test_reset.py:157-166] — deferred to Story 5.2 (security review document); broader project-wide concern, not specific to this route.

### Git intelligence summary

Last 5 commits on `main` (head of conversation):
- `61d5dc0 Merge branch 'retrospective-epic-1'` — closed Epic 1.
- `c88fa31 WIP` — placeholder commit on the epic-1 retro branch.
- `0a58442 retro E1` — retro deliverable for Epic 1.
- `060df66 feat: minor fixes to the CSFR token naming` — CSRF naming cleanup.
- `ca02146 fix: BFF drops offline_access scope + realm declares profile scope` — OAuth scope wire fix.

Last 5 commits on `epic-3` (the branch this story merges into):
- `61b28c5 Merge story 3.3 — RS ReadingSpeed model + /v1/reading-speed GET+PUT scope-gated` — Story 3.3 merged.
- `2f78bc5 chore: 3.3 code review — CR1–CR3 applied, mark done, log D66–D70`
- `7cf79ea feat: 3.3 RS /v1/reading-speed GET+PUT + ReadingSpeed model + 0001_init migration`
- `f23cb3e chore: 3.3 create story — RS ReadingSpeed model + migration + /v1/reading-speed GET/PUT`
- `119a25a Merge story 3.2 — RS oidc_bearer plugin + scope enforcement + synthetic-IdP harness`

**Implication for this story:** Stories 3.1, 3.2, and 3.3 sequentially added the RS's scaffold, JWT-bearer auth, and the `reading_speeds` table+API. **This story is the FIRST to touch `main.py` since 3.1** (3.2 and 3.3 added files but did not modify `main.py`). The diff is small (2 lines) and the integration is unambiguous — no rebase risk.

### Latest tech information

- **FastAPI** — `app.include_router(router)` is order-independent of `add_exception_handler` calls; routes added after handlers are still wrapped by them (FastAPI 0.135+ behavior — Starlette's `Router` lazily builds the middleware/handler stack on first request).
- **SQLAlchemy 2.x** — `delete(SQLModelClass)` without a `WHERE` clause issues a bare `DELETE FROM <table>` SQL statement. SQLite supports this; `result.rowcount` returns the deleted row count (verified in pytest with seeded rows). With `execution_options={"synchronize_session": False}`, the ORM's session-sync step is skipped (avoids loading every row into Python memory; same mitigation Story 3.3's service module documents).
- **pydantic-settings 2.x** — `bool` fields from env coerce `"true"` / `"True"` / `"1"` / `"yes"` / `"on"` to `True` and everything else (including `""`, `"false"`, `"0"`) to `False`. This is the v2 default and matches AC2's wording.
- **pytest-asyncio** — uses `asyncio_mode = "auto"` per `services/resource-server/pyproject.toml`; test functions just need `async def` and pytest discovers them. No `@pytest.mark.asyncio` decorators required.
- **httpx 0.28+** — `AsyncClient(transport=ASGITransport(app=app))` is the supported pattern for in-process ASGI testing.
- **PyJWT 2.10+ / PyJWKClient** — NOT used by this story's route (the test-reset route bypasses the JWT path entirely). Scenario 16 explicitly pins this non-interaction.

### Project Structure Notes

- New file `src/resource_server/api/test_reset.py` slots cleanly into the existing `api/` package alongside `health.py`, `reading_speed.py`, `v1/`, `v2/`, `schemas/`.
- New test file `tests/api/test_test_reset.py` — pytest will discover it via the `test_*.py` convention (the doubled `test_` prefix is fine; the module is `tests.api.test_test_reset` and pytest collects every test function inside).
- The RS does NOT have a CSRF middleware module to extend; contrast Story 1.12 which added `_CSRF_EXEMPT_PATHS` to the BFF's `auth/csrf.py`.
- No new `core/exceptions.py` entry; the auth failures emit `SESSION_EXPIRED` via direct `JSONResponse` (bespoke auth, not a domain exception).
- The RS's `models/entities/__init__.py` declares `__all__ = ["ReadingSpeed"]` (Story 3.3); no edits needed here.

### References

- [Source: epics.md#Story 3.4 lines 1282-1314] — the entire story spec.
- [Source: epics.md#AR32 line 97] — architectural requirement for the test-reset endpoint (BFF + RS halves).
- [Source: epics.md#Story 1.12 lines 666-704] — the BFF analog, which this story closely mirrors (with RS-specific deltas: no CSRF, no `auth_states`/`sessions`, only `reading_speeds`).
- [Source: epics.md#Story 3.6 lines (after 3.4)] — the downstream consumer that adds compose wiring + Playwright helpers + J4 spec.
- [Source: architecture.md#"POST /v1/test/reset (e2e profile only)" lines 1354-1360] — operational contract.
- [Source: architecture.md#Source-Tree Structure lines 903, 972] — canonical file paths for BFF + RS `test_reset.py`.
- [Source: architecture.md#API & Communication Patterns C5] — `ErrorCode` envelope; `session_expired` for 401.
- [Source: architecture.md#Logging conventions lines 781-788] — never log token material.
- [Source: services/resource-server/src/resource_server/core/config.py lines 93-94] — `enable_test_reset` / `test_reset_token` already declared.
- [Source: services/resource-server/src/resource_server/core/errors.py:27-31] — `ErrorCode.SESSION_EXPIRED` definition.
- [Source: services/resource-server/src/resource_server/auth/oidc_bearer.py:120-127] — the `SESSION_EXPIRED` envelope shape we mirror in `_unauthorized_response`.
- [Source: services/resource-server/src/resource_server/main.py:9-69] — the `main.py` file to extend with the `register_test_reset_router` call.
- [Source: services/resource-server/.env.example:55-59] — gating env vars already templated; `change-me` is the literal placeholder this story's AC1 rejects.
- [Source: services/resource-server/tests/conftest.py:75-111] — engine/session/client fixture patterns to mirror in `_build_test_context`.
- [Source: compose/app.yml] — `resource-server` profiles `[default, dev]` (Story 3.6 will add `e2e`).
- [Source: compose/app.e2e.yml] — BFF-only overlay today; Story 3.6 will extend.
- [Source: Justfile] — `default-config` and `e2e-config` recipes for compose validation.
- [Source: services/resource-server/pyproject.toml] — Python 3.14, pytest config, coverage gate `fail_under = 90`.
- [Source: services/resource-server/CLAUDE.md] — quality gate enumeration (ruff check + format + ty + pytest) before every commit.
- [Source: CLAUDE.md (root)] — project convention: `python` (not `python3`).
- [Source: services/bff/src/bff/api/test_reset.py] — BFF Story 1.12 implementation (reference, not shared code).
- [Source: services/bff/tests/api/test_test_reset.py] — BFF Story 1.12 test patterns (reference).
- [Source: _bmad-output/implementation-artifacts/1-12-bff-post-v1-test-reset-endpoint.md] — BFF Story 1.12 story file (reference).
- [Source: _bmad-output/implementation-artifacts/3-3-rs-reading-speed-model-migration-v1-reading-speed-get-put-scope-gated.md] — Story 3.3 dev log (reference for ReadingSpeed entity + service patterns).
- [Source: _bmad-output/implementation-artifacts/deferred-work.md] — D66–D70 from Story 3.3 review (RS-specific defers); D71 will be added by this story (BFF placeholder-reject parity).

### Project context reference

Project-context facts loaded at activation:
- BMAD_books accessibility/responsive design: OUT OF SCOPE (not relevant — this is a backend-only story with no UI surface).
- Backend archetype: `github.com/tommaso-meledina/fastapi-archetype` (Python 3.14 + FastAPI + SQLModel + uv + OTEL) — this story stays inside the archetype's conventions (FastAPI APIRouter, SQLModel entities, uv-managed deps).
- Python invocation: `python` (never `python3`) — applies to any inline command examples; the project's Dockerfile, compose healthchecks, and pytest commands already follow this convention.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- **Task 1 decision (placeholder gate):** implemented all three gates as specified — `enable_test_reset == True` AND `test_reset_token.strip() != ""` AND `test_reset_token.strip() != "change-me"`. The `_PLACEHOLDER_TOKEN: Final[str] = "change-me"` constant lives at module scope so a future contributor can find it via Find-References before changing the literal. WARN log classifiers differentiate the three skip reasons (`test_reset_token_empty` vs `test_reset_token_default_placeholder`). Scenario 4 in the test suite pins the placeholder-reject behavior; the BFF parity gap is logged as D71 (security review owns the back-port).
- **Task 2 decision (main.py wiring):** kept the diff to two lines — import added after `v2_router` import, helper call appended after `app.include_router(v2_router)`. No `build_app(cfg)` factory refactor (the conftest's global-`app` strategy still works because tests build fresh apps via `_build_test_context`).
- **Task 3 decision (test fixture pattern):** chose the Story-1.12-style `_build_test_context(enable, token)` helper over monkeypatching the global `app`. Each scenario builds a fresh `FastAPI` + fresh in-memory SQLite engine + fresh sessionmaker + fresh `AppSettings`, registers `app_exception_handler` and `validation_exception_handler` to mirror `main.py:65-66`, overrides both `get_session` and `_settings_dep`, then calls `register_test_reset_router`. No cross-test state leak, no `app.include_router` un-mount problem.
- **Task 3 decision (scenario 24 — commit-failure):** the `_FaultyCommitSession` proxy uses `__getattr__` for all attributes including `execute` (no explicit override) to keep `ty` happy with SQLAlchemy's overloaded `execute` signature. Only `commit` is overridden to raise. The test exercises both possible outcomes: an explicit ≥500 response OR an exception that bubbled out of the ASGI transport — either satisfies the "handler did not swallow" guarantee. The seeded row count is asserted unchanged at 1 post-call, proving rollback.
- **Bearer comparison:** uses `hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))` with NO `.strip()` on either side — secrets are compared verbatim. Empty/whitespace `TEST_RESET_TOKEN` is treated as gate-off at registration time (defense-in-depth), but a non-empty token with leading/trailing whitespace IS compared literally; scenario 19 enforces "no silent stripping of secrets".
- **`rowcount` access:** uses `getattr(result, "rowcount", -1)` per the story's type note — SQLAlchemy's `Result[Any]` static type does not declare `rowcount` even though the runtime `CursorResult` does. The `# ty: ignore[invalid-argument-type]` originally placed on `_delete(ReadingSpeed)` was removed when ty did not complain about it; ruff's `B008` and ty's overload checks both pass clean.
- **AC1 helper signature:** `register_test_reset_router(app: FastAPI, cfg: AppSettings) -> None` — exactly as specified. `__all__ = ["register_test_reset_router", "router"]`.
- **204 empty-body assertion:** scenario 13 originally asserted `content-length: "0"` but FastAPI's bare `Response(status_code=204)` omits the header (per RFC 7230 §3.3.2, optional for 204). Relaxed the assertion to just `response.content == b""` (the body itself is the load-bearing guarantee); added an inline comment explaining the RFC backing. Documented as intentional in the test's body comment.
- **JWT non-interaction (scenario 16):** confirmed via caplog filter `[r for r in caplog.records if r.name == _OIDC_BEARER_LOGGER]` returning `[]` — the JWT-validation path's logger never fires on the test-reset route. Pins the absence-of-JWT-coupling.
- **Coverage:** `src/resource_server/api/test_reset.py` 61/61 stmts → 100% (via `pytest --cov=resource_server.api.test_reset`); project total 98.21% (gate is 90%). Full RS suite: 268 tests, all green (was 242 at story start; this story adds 26 tests).
- **Gates run from `services/resource-server/`:**
  - `uv sync --frozen` → exit 0 (no dep changes; `pyproject.toml` untouched)
  - `uv run ruff check` → All checks passed!
  - `uv run ruff format --check` → 87 files already formatted (clean — one auto-format pass on the test file during dev)
  - `uv run ty check` → All checks passed!
  - `uv run pytest --cov` → 268 passed, 98.21% coverage
- **Compose gates run from worktree root:**
  - `docker compose --profile default config` → valid; `resource-server` service shows `ENABLE_TEST_RESET: "false"` and `TEST_RESET_TOKEN: change-me` (both gates fail → route not mounted; default profile is safe).
  - `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e config` → valid; `resource-server` is NOT listed under the e2e profile (the base service still has `profiles: [default, dev]` — Story 3.6 will extend that). BFF retains `ENABLE_TEST_RESET=true` via the existing overlay. Confirms the "deferred to 3.6" boundary.
  - The validation required a transient `.env` file in the worktree (gitignored). Created by copying the repo-root `.env` + `services/bff/.env` + falling back to `services/resource-server/.env.example` for the RS per-service file (the RS one is gitignored and absent from the source repo). All transient `.env` files removed before commit; `git status` shows only the intended changes.
- **Deferred-work log:** added D71 (BFF placeholder-reject parity — owned by Story 5.2), D72 (405-via-wrong-method test coverage — test-quality cleanup), D73 (case-sensitive Bearer prefix vs RFC 6750 — owned by Story 5.2).
- **Python invocation convention:** all command examples and inline documentation written in this story (story file, code docstrings, dev log) use `python` — never `python3` — per `CLAUDE.md` (root). The existing Dockerfile / compose healthchecks / pytest commands already followed this convention; nothing changed.
- **Python `assert` in production code:** the `assert auth_header is not None` line in `test_reset.py:138` is a `ty` narrowing hint (the `_classify_auth_failure` check above ensures the header is non-None). Ruff's `S101` rule (`bandit-style assert usage`) is not enabled in this project's `[tool.ruff.lint.select]` (checked `pyproject.toml:53-62`); the `noqa: S101` comment makes the intent explicit for future reviewers.

### File List

**New files (created by this story):**
- `services/resource-server/src/resource_server/api/test_reset.py` — `POST /v1/test/reset` handler + `register_test_reset_router(app, cfg)` helper + `_classify_auth_failure` / `_unauthorized_response` / `_settings_dep` helpers. Module docstring describes purpose, gating (three gates including the `change-me` placeholder reject), auth, safety, and source references.
- `services/resource-server/tests/api/test_test_reset.py` — pytest module covering all 25 AC10 scenarios plus one direct `_settings_dep` coverage test (26 tests total). Doubled `test_` prefix is intentional (pytest discovers it; the RS route module is `test_reset.py` without the prefix). Helper `_build_test_context(enable, token)` builds a fresh `FastAPI` app + in-memory SQLite engine per test for full isolation.

**Modified files:**
- `services/resource-server/src/resource_server/main.py` — added `from resource_server.api.test_reset import register_test_reset_router` import (line 11) and a single `register_test_reset_router(app, settings)` call after `app.include_router(v2_router)` (line 70). Two-line diff.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flipped `3-4-rs-post-v1-test-reset-endpoint: backlog` → `ready-for-dev` → `in-progress` → `review` across the workflow.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended D71 (BFF placeholder-reject parity), D72 (405-via-wrong-method test coverage), D73 (case-sensitive Bearer prefix).

**NOT modified (intentional — per story spec):**
- `services/resource-server/src/resource_server/core/config.py` — `enable_test_reset` (line 93) and `test_reset_token` (line 94) were already declared by Story 3.1.
- `services/resource-server/.env.example` — `ENABLE_TEST_RESET=false` and `TEST_RESET_TOKEN=change-me` were already present (lines 58-59, Story 3.1).
- `services/resource-server/pyproject.toml` — no new dependencies.
- `services/resource-server/src/resource_server/api/v1/__init__.py` — the test-reset router is mounted into `app` directly via the helper, NOT included into `v1_router`.
- `services/resource-server/src/resource_server/services/reading_speed_service.py` — no truncate method added; the truncate is handler-local in `api/test_reset.py`.
- `services/resource-server/src/resource_server/models/entities/reading_speed.py` — schema unchanged from Story 3.3.
- Alembic migrations — no schema changes; the `0001_init` from Story 3.3 already creates `reading_speeds`.
- `compose/app.yml` / `compose/app.e2e.yml` / `Justfile` — all deferred to Story 3.6 per epic line 1302-1304.
