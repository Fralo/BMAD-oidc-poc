# Remove Rate Limiting — Changeset Analysis

This document describes every change required to completely remove the rate-limiting capability (slowapi) from resource-server, along with cascading implications.

---

## 1. File to Delete

| File | Reason |
|------|--------|
| `src/resource_server/core/rate_limit.py` | Entire file is the `Limiter` instance; no other purpose. |
| `tests/core/test_rate_limit.py` | All six tests exercise rate-limiting behavior exclusively. |

---

## 2. Source Files to Edit

### 2.1 `src/resource_server/core/errors.py`

| Line(s) | Change |
|----------|--------|
| 7 | Remove `from slowapi.errors import RateLimitExceeded` import. |
| 12 | Remove `RATE_LIMITED = ("RATE_LIMITED", "Rate limit exceeded", 429)` enum member. |
| 49–60 | Remove the entire `rate_limit_exceeded_handler` function. |

After removal, the `cast` import is still used by `app_exception_handler` and `validation_exception_handler`, so it stays. The `Request` import is still used by the remaining handlers, so it stays.

### 2.2 `src/resource_server/main.py`

| Line(s) | Change |
|----------|--------|
| 9 | Remove `from slowapi.errors import RateLimitExceeded`. |
| 26 | Remove `rate_limit_exceeded_handler` from the errors import block. |
| 29 | Remove `from resource_server.core.rate_limit import limiter`. |
| 81 | Remove `app.state.limiter = limiter`. |
| 83 | Remove `app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)`. |

No other changes needed — the remaining exception handlers (`AppException`, `RequestValidationError`) stay.

### 2.3 `src/resource_server/core/config.py`

| Line(s) | Change |
|----------|--------|
| 73–74 | Remove the two `AppSettings` fields: `rate_limit_get_dummies: str = "100/minute"` and `rate_limit_post_dummies: str = "10/minute"`. |

### 2.4 `src/resource_server/api/v1/dummy_routes.py`

| Line(s) | Change | Detail |
|----------|--------|--------|
| 1 | Remove `Request` and `Response` from the `fastapi` import. | After removal, the import becomes `from fastapi import APIRouter, Depends, status`. |
| 5 | Remove `from resource_server.core.config import settings`. | Only used for `settings.rate_limit_*` in the `@limiter.limit(...)` decorators. |
| 8 | Remove `from resource_server.core.rate_limit import limiter`. | |
| 28 | Remove `@limiter.limit(settings.rate_limit_get_dummies)` decorator from `list_dummies`. | |
| 30–31 | Remove `request: Request` and `response: Response` parameters from `list_dummies`. | These parameters exist solely for slowapi; FastAPI does not need them for this route. |
| 41 | Remove `@limiter.limit(settings.rate_limit_post_dummies)` decorator from `create_dummy`. | |
| 43, 45 | Remove `request: Request` and `response: Response` parameters from `create_dummy`. | |

**After this change**, the route signatures simplify to:

```python
async def list_dummies(
    svc: DummyServiceV1 = Depends(get_dummy_service_v1),
) -> list[GetDummiesResponse]:
```

```python
async def create_dummy(
    dummy: PostDummiesRequest,
    principal: Principal = Depends(require_auth),
    svc: DummyServiceV1 = Depends(get_dummy_service_v1),
) -> PostDummiesResponse:
```

The `update_dummy` route is unaffected — it already has no rate limiting, no `Request`, and no `Response`.

### 2.5 `src/resource_server/api/v2/dummy_routes.py`

Analogous changes to v1:

| Line(s) | Change |
|----------|--------|
| 1 | Remove `Request` and `Response` from the `fastapi` import. The import becomes `from fastapi import APIRouter, Depends, status`. |
| 5 | Remove `from resource_server.core.config import settings`. |
| 7 | Remove `from resource_server.core.rate_limit import limiter`. |
| 26 | Remove `@limiter.limit(settings.rate_limit_get_dummies)` decorator. |
| 28–29 | Remove `request: Request` and `response: Response` from `list_dummies`. |
| 39 | Remove `@limiter.limit(settings.rate_limit_post_dummies)` decorator. |
| 41, 43 | Remove `request: Request` and `response: Response` from `create_dummy`. |

**After this change**, the route signatures simplify to:

```python
async def list_dummies(
    svc: DummyServiceV2 = Depends(get_dummy_service_v2),
) -> list[GetDummiesResponse]:
```

```python
async def create_dummy(
    dummy: PostDummiesRequest,
    principal: Principal = _depends_require_admin,
    svc: DummyServiceV2 = Depends(get_dummy_service_v2),
) -> PostDummiesResponse:
```

---

## 3. Test Files to Edit

### 3.1 `tests/conftest.py`

| Line(s) | Change | Detail |
|----------|--------|--------|
| 5 | Remove `Request` and `Response` from `from fastapi import APIRouter, Depends, Request, Response`. The import becomes `from fastapi import APIRouter, Depends`. | |
| 18 | Remove `from resource_server.core.rate_limit import limiter`. | |
| 33 | Remove `@limiter.limit("100/minute")` from `_stub_get_open`. | |
| 34 | Remove `request: Request` and `response: Response` from `_stub_get_open` signature. | |
| 39–40 | Remove `@limiter.limit("10/minute")` from `_stub_post_open`. | |
| 42, 43 | Remove `request: Request` and `response: Response` from `_stub_post_open` signature. | |
| 48 | Remove `@limiter.limit("10/minute")` from `_stub_post_auth_required`. | |
| 49–51 | Remove `request: Request` and `response: Response` from `_stub_post_auth_required` signature. | |
| 60 | Remove `@limiter.limit("10/minute")` from `_stub_post_admin_required`. | |
| 61–63 | Remove `request: Request` and `response: Response` from `_stub_post_admin_required` signature. | |
| 106 | Remove `limiter.reset()` from the `client_fixture`. | |

### 3.2 `tests/auth/conftest.py`

| Line(s) | Change |
|----------|--------|
| 16 | Remove `from resource_server.core.rate_limit import limiter`. |
| 127 | Remove `limiter.reset()` from `entra_client_fixture`. |

### 3.3 `tests/auth/test_entra_integration.py`

| Line(s) | Change |
|----------|--------|
| 32 | Remove `from resource_server.core.rate_limit import limiter`. |
| 169 | Remove `limiter.reset()` from `entra_integration_client_fixture`. |

### 3.4 `tests/api/test_profile_service_selection.py`

| Line(s) | Change |
|----------|--------|
| 9 | Remove `from resource_server.core.rate_limit import limiter`. |
| 36 | Remove `limiter.reset()` from `client_with_mock_v1_simple_fixture`. |
| 91 | Remove `limiter.reset()` from `client_with_mock_v2_fixture`. |

---

## 4. Dependency to Remove

### 4.1 `pyproject.toml`

| Line | Change |
|------|--------|
| 20 | Remove `"slowapi>=0.1.9"` from `[project] dependencies`. |

### 4.2 Lock file

Run `uv lock` (or `uv sync`) after editing `pyproject.toml` to regenerate `uv.lock` without slowapi.

---

## 5. Configuration and Documentation Files to Edit

### 5.1 `.env.example`

Remove lines 26–28 (the rate-limiting comment block):

```
# Rate Limiting (slowapi — format: "N/period" where period is second, minute, hour, day)
# RATE_LIMIT_GET_DUMMIES=100/minute   (default — GET /v{n}/dummies)
# RATE_LIMIT_POST_DUMMIES=10/minute   (default — POST /v{n}/dummies)
```

### 5.2 `README.md`

- **Line 28**: Remove "Per-endpoint rate limiting with environment-configurable thresholds" from the capabilities bullet list.
- **Lines 220–232**: Remove the entire "### Rate Limiting" section.
- **Line 169**: Remove "rate-limit violations" from the structured error handling description (reword to: "Custom exception handlers cover application errors and validation failures.").
- **Line 453**: Remove "rate limiting" from the sentence "New resources inherit tracing, metrics, error handling, rate limiting, and AOP logging automatically." in the Extension Guide.
- **Lines 400–441** (Extension Guide step 7 "Add the routes"): Rewrite the example route code to remove `@limiter.limit(...)` decorators, `Request`/`Response` parameters, and the `from ...rate_limit import limiter` / `from ...config import settings` imports.

### 5.3 `PROJECT_CONTEXT.md`

- **Line 31** (Technology Stack table): Remove the `slowapi` row: `| slowapi | >=0.1.9 | Per-endpoint rate limiting |`.
- **Line 82** (Project Structure): Remove `│   └── rate_limit.py` from the tree listing.
- **Section 4 (Structured Error Handling)**: Remove `RateLimitExceeded` from the list of three global exception handlers (line 199). Reword to: "Two global exception handlers registered in `main.py`: `AppException`, `RequestValidationError`."
- **Section 9 (Rate Limiting)**: Remove the entire section (lines 235–239).
- **Endpoint table** (lines 158–169): Remove the "Rate limit setting" column entirely from the endpoint table.
- **Line 296** (Testing section): Remove "`limiter.reset()` is called in the client fixture to prevent cross-test pollution."
- **Line 375** (Dependency injection section): Remove "Rate limiting: `@limiter.limit(settings.rate_limit_xxx)` decorator."
- **Lines 436, 440** (Adding a New Resource): Remove steps and references related to rate limiting: "Rate limits and auth as needed" (line 436) and "Add `rate_limit_get_widgets` / `rate_limit_post_widgets` fields..." (line 440).

### 5.4 `ARCH_DECISIONS.md`

- **Line 101** (AD 07): Remove `RateLimitExceeded` from the list of global exception handlers. Reword to: "...global exception handlers registered in `main.py`: `AppException`, `RequestValidationError`."
- **Lines 187–199** (AD 14): Remove the entire "AD 14 - Rate Limiting" section.
- **Line 347** (AD 24): Remove "`limiter.reset()` prevents rate-limit state leakage between tests." from the Testing AD.

### 5.5 `RELEASE_NOTES.md`

- **Line 119**: Optionally remove or keep the historical entry "add per-endpoint rate limiting with slowapi (Epic 9)". This is a changelog record of past work — removing it is a matter of preference, but keeping it is standard practice for changelogs.
- **Line 164**: Same for "code review fixes for rate limiting (Epic 9)".

---

## 6. Scripts to Edit

### 6.1 `scripts/remove_demo.py`

The `_edit_config` function (lines 93–100) removes the `rate_limit_get_dummies` and `rate_limit_post_dummies` fields from `config.py`. After rate limiting is removed globally, these fields no longer exist, so this edit function becomes a no-op. Additionally, `_edit_env_example` (lines 146–154) filters out `RATE_LIMIT_*` lines.

| Change | Detail |
|--------|--------|
| Remove `_edit_config` function body or update it. | The rate-limit fields will already be gone from `config.py`. The function should either be removed or modified to only handle non-rate-limit config edits if any remain. Currently it does nothing else, so it can be removed entirely along with its entry in `_EDIT_DISPATCH`. |
| Update `_edit_env_example`. | The `RATE_LIMIT_*` lines will already be gone from `.env.example`. The filter logic referencing them becomes dead code. If the function has no other edits to make, it can be removed along with its `_EDIT_DISPATCH` entry. |

### 6.2 `scripts/build_template.py`

The embedded `_POST_GEN_HOOK_CONTENT` string (lines 348–529) contains a `_edit_config` function and `_edit_env_example` function with the same rate-limit removal logic. These need the same cleanup as `remove_demo.py`.

The `_TEMPLATE_README` string (lines 531–749) references rate limiting in several places:

| Location in template README | Change |
|-----------------------------|--------|
| Capabilities list: `"- **Rate limiting** per endpoint, configurable via env vars"` | Remove the bullet. |
| Extension Guide step 5 (Routes example): imports `limiter`, `settings`, uses `@limiter.limit(...)`, `Request`, `Response` | Rewrite the example route code to remove all rate-limiting artifacts. Simplified routes should not import `limiter`, `settings`, `Request`, or `Response`. |
| Final sentence: `"New resources inherit tracing, metrics, error handling, rate limiting, and AOP logging automatically."` | Remove "rate limiting" from the list. |

---

## 7. Planning Artifacts (`.bmad/`)

These are historical planning documents, not runtime code. They reference rate limiting in:

- `.bmad/planning-artifacts/epics/epic-9-rate-limiting.md` (entire file)
- `.bmad/planning-artifacts/epics/epic-list.md` (Epic 9 entry)
- `.bmad/planning-artifacts/epics/index.md` (Epic 9 link)
- `.bmad/planning-artifacts/epics/requirements-inventory.md` (FR30–FR32)
- `.bmad/planning-artifacts/prd/functional-requirements.md` (FR30–FR32, FR52–FR53)
- `.bmad/implementation-artifacts/9-1-per-endpoint-rate-limiting*.md`

**Recommendation**: These are historical artifacts and can be left as-is (they document past decisions), or marked as superseded. This is a matter of preference.

---

## 8. Cascading Implications

### 8.1 `Request` and `Response` parameters become unnecessary on route functions

This is the most significant ergonomic improvement. The `request: Request` and `response: Response` parameters on rate-limited routes exist **solely** because slowapi requires them. Without rate limiting:

- **4 production route functions** lose these parameters (v1 GET, v1 POST, v2 GET, v2 POST).
- **4 test stub route functions** in `tests/conftest.py` lose these parameters.
- Route signatures become cleaner and more focused on their actual dependencies.

The `update_dummy` route in v1 already has no `Request`/`Response` (it was never rate-limited), confirming this pattern.

### 8.2 `limiter.reset()` calls become unnecessary in test fixtures

Five test fixtures currently call `limiter.reset()` to prevent rate-limit state from leaking between tests. Without the limiter, these calls are simply removed — no replacement is needed.

### 8.3 The `RATE_LIMITED` error code is eliminated

The `ErrorCode.RATE_LIMITED` enum member and its handler are removed. The structured error response for 429 status codes is no longer produced. If rate limiting is later reintroduced at the infrastructure level (e.g., reverse proxy), the application will not produce its own 429 responses.

### 8.4 The `settings` import is removed from route modules

In both `api/v1/dummy_routes.py` and `api/v2/dummy_routes.py`, the `from resource_server.core.config import settings` import exists **only** to feed rate-limit strings to `@limiter.limit(...)`. After removal, these route modules no longer import `settings` at all.

### 8.5 `app.state.limiter` is no longer set

slowapi requires `app.state.limiter = limiter` for its middleware integration. This line is removed from `main.py`. No other code reads `app.state.limiter`.

### 8.6 No response headers for rate-limit status

Clients currently receive `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers on rate-limited endpoints. These headers will no longer be present.

### 8.7 Extension Guide simplifies

The "Adding a New Resource" guide in `PROJECT_CONTEXT.md` and the template README no longer need to mention rate-limit config fields, `@limiter.limit()` decorators, `Request`/`Response` parameters, or `limiter`/`settings` imports. New resource routes become simpler.

### 8.8 Docker Compose `.env` is unaffected

The `compose/.env` file does not contain rate-limiting variables — it only has database, OTEL, and app-level settings.

---

## 9. Summary: Change Count

| Category | Files deleted | Files edited |
|----------|:------------:|:------------:|
| Source code | 1 | 5 |
| Tests | 1 | 4 |
| Config/docs | 0 | 6 |
| Scripts | 0 | 2 |
| Dependencies | 0 | 1 (`pyproject.toml`) + lock regen |
| **Total** | **2** | **18** |

---

## 10. Verification Checklist

After applying all changes:

1. `uv sync` — confirms slowapi is removed from the virtual environment.
2. `uv run ruff check` — no lint errors.
3. `uv run ruff format --check` — formatting is clean.
4. `uv run ty check` — no type errors or warnings.
5. `uv run pytest` — all remaining tests pass (the 6 deleted rate-limit tests are gone; no other test depends on rate-limiting behavior).
6. Verify no remaining references to `slowapi`, `limiter`, `rate_limit`, or `RateLimitExceeded` in `src/` or `tests/` (a `rg -i "slowapi|limiter|rate.limit" src/ tests/` should return zero results).
