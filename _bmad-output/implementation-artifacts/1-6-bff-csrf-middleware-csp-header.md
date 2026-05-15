# Story 1.6: BFF CSRF middleware + CSP header

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a security-aware reviewer,
I want state-changing requests without a valid CSRF header to be rejected with a 403 `csrf_invalid` envelope, and SPA-served responses to carry the documented Content-Security-Policy header,
so that the BFF's cookie-session surface meets the documented security posture (architecture A5 + A8) even before any domain features exist.

## Acceptance Criteria

**AC1 — Module surface.** Two new modules are added to the existing `services/bff/src/bff/auth/` package (created by Story 1.5 — see `src/bff/auth/{__init__.py,keycloak_cookie_session.py,pkce.py}`):

- `services/bff/src/bff/auth/csrf.py` (NEW) — exposes a Starlette `BaseHTTPMiddleware` subclass `CsrfMiddleware`. **Single** middleware class; **no** stand-alone helper functions exported except a `_constant_time_eq(a, b)` private helper (use `hmac.compare_digest`).
- `services/bff/src/bff/middleware/security_headers.py` (NEW) — exposes a `SecurityHeadersMiddleware` (Starlette `BaseHTTPMiddleware` subclass) that attaches the documented `Content-Security-Policy` header to SPA-serving responses. The `middleware/` subpackage is NEW; add `services/bff/src/bff/middleware/__init__.py` (empty). **Discrepancy:** architecture §Cross-Cutting Concerns Mapping line 1193 places the CSP middleware in `src/bff/app.py`; the BFF's actual entry point is `src/bff/main.py` (Story 1.3 precedent). Place the middleware in a dedicated module under `middleware/` and register it from `main.py`. Document this in Dev Notes.

`bff/main.py` (existing — see main.py:31–53) is the **only** existing file modified outside the new modules: add two `app.add_middleware(...)` calls (CSRF first registered → executes LAST in Starlette's onion; SecurityHeaders registered next so it runs INSIDE the CSRF middleware and never sees a 403 response without CSP — see "Middleware ordering" in Dev Notes). The existing CORS middleware install (main.py:38–46), the exception handlers (main.py:48–49), and the router includes (main.py:50–53) are untouched.

[Source: epics.md#Story 1.6 lines 396–430; architecture.md#Authentication & Security A5 line 351; architecture.md#Authentication & Security A8 line 354; architecture.md#Cross-Cutting Concerns Mapping lines 1192–1193; architecture.md#Complete Project Directory Structure line 913; services/bff/src/bff/main.py:31–53.]

**AC2 — CSRF middleware accepts safe methods unconditionally.** Given any HTTP request whose method is `GET`, `HEAD`, or `OPTIONS`, the `CsrfMiddleware` passes the request through to the downstream `call_next` without any cookie or header inspection. The response is returned unchanged (no `Set-Cookie`, no `Vary` tweak). Verified by parametrized test against a stub endpoint (use the existing `_test_router` at `tests/conftest.py:34–48` — its `GET /test/open` is a perfect target).

[Source: epics.md#Story 1.6 lines 420–421; architecture.md#Authentication & Security A5 line 351 (double-submit on **state-changing** requests).]

**AC3 — Happy-path state-changing request (POST/PUT/PATCH/DELETE).** Given a request whose method is `POST`, `PUT`, `PATCH`, or `DELETE` AND:

1. The request carries the CSRF cookie `BFF_CSRF_COOKIE_NAME` (default: `bff_csrf`) with a non-empty value, AND
2. The request carries the header `X-CSRF-Token` (case-insensitive per RFC 7230 §3.2; Starlette's `Headers` mapping is case-insensitive by construction), AND
3. `hmac.compare_digest(header_value, cookie_value)` is `True`, AND
4. The request's `Origin` header (preferred) OR `Referer` header (fallback when `Origin` is absent) parses to a URL whose scheme+host+port equal `BFF_BASE_URL`'s scheme+host+port (use `urllib.parse.urlparse` — compare `(scheme, hostname, port)` triples; **ignore path/query/fragment**),

then the middleware calls `await call_next(request)` and returns the downstream response unchanged.

**Same-origin determination details:**
- `BFF_BASE_URL = "http://localhost:8000"` → expected triple `("http", "localhost", 8000)`. A request with `Origin: http://localhost:8000` → match. A request with `Origin: http://localhost` (no port) → mismatch (port 80 ≠ 8000).
- `Referer` is consulted ONLY when `Origin` is absent or equal to `"null"` (the spec value the browser sends for sandboxed iframes / data-URLs).
- Both `Origin` AND `Referer` absent on a state-changing request → **403 `csrf_invalid`** (NOT a pass-through). Browsers always send at least one for cross-document POSTs from a real page; absence indicates a script-injected request that the architecture forbids.

[Source: epics.md#Story 1.6 lines 413–414; architecture.md#Authentication & Security A5 line 351 ("Origin/Referer check as defense in depth"); services/bff/src/bff/core/config.py:80 (`bff_base_url`).]

**AC4 — Missing `X-CSRF-Token` header → 403 `csrf_invalid`.** Given a state-changing request whose `X-CSRF-Token` header is absent OR empty string, the middleware short-circuits and returns a `JSONResponse(status_code=403, content={"errorCode": "csrf_invalid", "message": "CSRF token missing or invalid", "detail": null})`. No `Set-Cookie` is emitted (the cookie is still valid — only the header is missing). The failure is logged at **WARN** with classifier `csrf_header_missing path=<request.url.path> method=<method>` (path is safe to log per architecture lines 783–788; never log the cookie or header value). `call_next` is NOT invoked — the downstream handler does not run.

[Source: epics.md#Story 1.6 lines 407–408; architecture.md#Authentication & Security A5 line 351; architecture.md#Format Patterns line 684 (403 / `csrf_invalid`); services/bff/src/bff/core/errors.py:9–26 (envelope shape).]

**AC5 — Header/cookie value mismatch → 403 `csrf_invalid`.** Given a state-changing request whose `X-CSRF-Token` header value does NOT equal the `BFF_CSRF_COOKIE_NAME` cookie value (use `hmac.compare_digest` — constant-time comparison resists timing oracles), OR the cookie is absent, OR the cookie value is empty, the middleware returns the same 403 envelope as AC4. Log classifier: `csrf_token_mismatch`. **Critically:** `compare_digest` MUST be called with `bytes` or `str` of equal length — short-circuit on `len(header) != len(cookie)` before the comparison would otherwise leak a length oracle, OR (preferred) feed both through `str.encode("utf-8")` and let `compare_digest` short-circuit-safely.

[Source: epics.md#Story 1.6 lines 410–411; architecture.md#Authentication & Security A5 line 351.]

**AC6 — Cross-origin Origin/Referer → 403 `csrf_invalid`.** Given a state-changing request that satisfies AC3's header/cookie match BUT whose `Origin` (or fallback `Referer`) does NOT match `BFF_BASE_URL`'s scheme+host+port triple, the middleware returns the 403 envelope. Log classifier: `csrf_origin_mismatch origin=<origin header value, untruncated — Origin is RFC 6454 ASCII-only, no PII> referer=<referer or "(none)">`. The Origin header itself is safe to log per architecture lines 781–788 (no PII content in an Origin header by definition — it's just `scheme://host[:port]`). The Referer MAY carry a path; truncate to `urlparse(referer).hostname` before logging to avoid leaking the path query string.

[Source: epics.md#Story 1.6 lines 416–418; architecture.md#Authentication & Security A5 line 351; architecture.md#Logging conventions lines 781–788.]

**AC7 — `ErrorCode.CSRF_INVALID` added to the enum.** `services/bff/src/bff/core/errors.py` gains a new enum member exactly: `CSRF_INVALID = ("csrf_invalid", "CSRF token missing or invalid", 403)`. Wire-value is lower_snake_case per architecture §C5 line 408. Insert the member alphabetically-after `AUTH_STATE_INVALID` (which was added by Story 1.5 at errors.py:26) — preserves the documented contract order without renumbering. The middleware uses `ErrorCode.CSRF_INVALID.code` / `.message` / `.http_status` to build the response body (matches the pattern at api/auth.py:84–101 and api/me.py:36–44). [Source: architecture.md#API & Communication Patterns C5 line 408; services/bff/src/bff/core/errors.py:9–26 (current enum surface).]

**AC8 — CSP header attached to SPA-serving routes only.** `SecurityHeadersMiddleware` inspects each response after `call_next` returns. It adds the header

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

(single line, **exactly** that string — assertion is byte-for-byte in tests; see AC11 scenario `csp_header_value_byte_for_byte`) ONLY when the response satisfies BOTH:

1. The request's `Accept` header includes `text/html` (matches the architecture's "CSP only on HTML responses" rule at epics line 429 + architecture line 1352), AND
2. The request path does NOT start with `/auth/`, `/api/`, `/v1/`, OR `/health` (these are JSON-only API namespaces — see main.py:50–53 + architecture §Operational Details "BFF routing precedence" lines 1343–1349).

The header is added via `response.headers["Content-Security-Policy"] = "..."`. **No** `Vary` header tweak (FastAPI/Starlette does not auto-cache, so Vary is decorative). **No** `Content-Security-Policy-Report-Only` variant (not requested by AC).

**Until Story 1.10+ adds a static-file mount at `/`, no live SPA-serving route exists.** The middleware must still:
- Add CSP to the catch-all 404 envelope for unknown paths IF the request carried `Accept: text/html` (defensive — once SPA static mount lands in Story 1.10, the same paths will start serving HTML; the middleware is path-pattern-driven, not content-type-aware).
- NOT add CSP to JSON 404s emitted under `/auth/*`, `/api/*`, `/v1/*`, `/health` (those carry `Content-Type: application/json` by handler convention; the path exclusion catches them).

The middleware does NOT mutate any other response header. It is a **pure additive** middleware.

[Source: epics.md#Story 1.6 lines 423–425, 429; architecture.md#Authentication & Security A8 line 354; architecture.md#Operational Details "BFF routing precedence" lines 1343–1349; architecture.md#Cross-Cutting Concerns Mapping line 1193.]

**AC9 — Wired into `main.py` with correct ordering.** `services/bff/src/bff/main.py` gains exactly two new `app.add_middleware(...)` calls inserted BETWEEN the CORS install (main.py:38–46) and the exception-handler registration (main.py:48–49):

```python
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CsrfMiddleware)
```

**Order matters and is non-obvious.** Starlette's middleware stack is a LIFO onion: the LAST middleware added runs FIRST on the incoming request and LAST on the outgoing response. By adding `SecurityHeadersMiddleware` first and `CsrfMiddleware` second:

- Incoming: `CORS → CSRF → SecurityHeaders → router` (CSRF runs before the SPA-serving handler; SecurityHeaders runs after — pass-through on the way in, header-attach on the way out).
- Outgoing: `router → SecurityHeaders → CSRF → CORS` (SecurityHeaders sees the eventual response and attaches CSP; CSRF leaves it untouched on the way out; CORS lifts the cross-origin headers — though CORS is disabled in default config).
- **403 path:** when CSRF short-circuits, the response bypasses the router AND `SecurityHeaders` (because SecurityHeaders is INNER to CSRF in the onion — CSRF's short-circuit happens BEFORE it would dispatch into SecurityHeaders). The 403 `csrf_invalid` envelope therefore does NOT carry CSP. This is correct: CSP only applies to HTML; the 403 is JSON.

The two new imports at the top of `main.py`: `from bff.auth.csrf import CsrfMiddleware` and `from bff.middleware.security_headers import SecurityHeadersMiddleware`. Imports follow isort/ruff order (first-party last, alphabetical within group — see existing main.py:1–19 for the pattern).

[Source: services/bff/src/bff/main.py:31–53 (existing structure); Starlette docs — BaseHTTPMiddleware onion ordering.]

**AC10 — Existing endpoints remain functional with CSRF active.** Adding `CsrfMiddleware` MUST NOT break any of the currently-passing 223+ tests. In particular:

- `GET /api/me` (api/me.py:51): safe-method, passes AC2 unconditionally.
- `GET /auth/login` (api/auth.py:104): safe-method, passes AC2.
- `GET /auth/callback` (api/auth.py:148): safe-method, passes AC2.
- `GET /health` (api/health.py:141): safe-method, passes AC2.
- `GET /test/open` AND `POST /test/open` (tests/conftest.py:37,44): the `POST` was added as a fixture for general route testing. **This story extends `tests/conftest.py` to make the test client send the CSRF cookie + header automatically on state-changing requests**, OR the existing `POST /test/open` test (`tests/api/test_cors.py`) is updated to add the cookie/header manually. **Recommended:** add a `client_with_csrf` fixture (alongside `client` and `client_no_redirects`) that pre-seeds `bff_csrf=test-csrf` cookie and sets `X-CSRF-Token: test-csrf` + `Origin: http://test` default headers. Migrate `tests/api/test_cors.py`'s POST tests to use it. **Do NOT** modify the default `client` fixture's behavior — many tests inspect cookies/headers explicitly and would break.

A separate test (Task 5 scenario `existing_post_open_requires_csrf`) asserts that the existing `POST /test/open` route NOW returns 403 `csrf_invalid` when called via the bare `client` fixture without cookies/header. This is the explicit demonstration that the middleware is active.

[Source: services/bff/tests/conftest.py:34–48 (stub router); services/bff/tests/api/test_cors.py (existing POST tests); architecture.md#Authentication & Security A5 line 351.]

**AC11 — Test coverage matrix.** Tests under `services/bff/tests/auth/test_csrf.py` (NEW) AND `services/bff/tests/middleware/test_security_headers.py` (NEW; `tests/middleware/__init__.py` empty) cover the scenarios enumerated in epics line 429, expanded to:

| # | Scenario | Method | Cookie | Header | Origin | Expected | Asserted |
|---|---|---|---|---|---|---|---|
| 1 | Safe GET no cookie no header | GET | — | — | — | 200 (downstream) | `response.status_code == 200`; downstream handler ran |
| 2 | Safe HEAD no header | HEAD | — | — | — | 200 | passthrough |
| 3 | Safe OPTIONS no header | OPTIONS | — | — | — | 200/405 (per route) | passthrough — middleware does NOT short-circuit |
| 4 | POST happy path | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `http://test` | 201 (downstream) | downstream handler ran; response body = stub payload |
| 5 | PUT happy path | PUT | `bff_csrf=abc` | `X-CSRF-Token: abc` | `http://test` | 200/405 | passthrough (no PUT route — but middleware passes; route emits 405) |
| 6 | PATCH happy path | PATCH | `bff_csrf=abc` | `X-CSRF-Token: abc` | `http://test` | 405 | passthrough |
| 7 | DELETE happy path | DELETE | `bff_csrf=abc` | `X-CSRF-Token: abc` | `http://test` | 405 | passthrough |
| 8 | POST missing header | POST | `bff_csrf=abc` | — | `http://test` | **403** | envelope `{"errorCode":"csrf_invalid","message":...,"detail":null}`; downstream NOT called; WARN log `csrf_header_missing` captured via `caplog` |
| 9 | POST empty header | POST | `bff_csrf=abc` | `X-CSRF-Token:` (empty) | `http://test` | **403** | same as #8 |
| 10 | POST missing cookie | POST | — | `X-CSRF-Token: abc` | `http://test` | **403** | classifier `csrf_token_mismatch` |
| 11 | POST empty cookie | POST | `bff_csrf=` | `X-CSRF-Token: abc` | `http://test` | **403** | classifier `csrf_token_mismatch` |
| 12 | POST header/cookie mismatch | POST | `bff_csrf=abc` | `X-CSRF-Token: xyz` | `http://test` | **403** | classifier `csrf_token_mismatch` |
| 13 | POST cross-origin Origin | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `https://evil.example` | **403** | classifier `csrf_origin_mismatch` |
| 14 | POST cross-port Origin | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `http://test:9999` | **403** | port differs → mismatch |
| 15 | POST scheme mismatch | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `https://test` | **403** | scheme differs → mismatch |
| 16 | POST Origin absent, Referer same-origin | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | (no Origin); `Referer: http://test/page` | 201 | passthrough |
| 17 | POST Origin absent, Referer cross-origin | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | (no Origin); `Referer: https://evil.example/x` | **403** | classifier `csrf_origin_mismatch` |
| 18 | POST Origin absent, Referer absent | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | (no Origin/Referer) | **403** | classifier `csrf_origin_mismatch` |
| 19 | POST `Origin: null` (sandboxed iframe) | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `Origin: null`; (no Referer) | **403** | `null` ≠ `http://test` |
| 20 | POST `Origin: null`, Referer same-origin | POST | `bff_csrf=abc` | `X-CSRF-Token: abc` | `Origin: null`; `Referer: http://test/x` | 201 | fallback to Referer succeeds |
| 21 | POST constant-time compare on length difference | POST | `bff_csrf=abc` | `X-CSRF-Token: abcd` | `http://test` | **403** | response time variance bounded (assert via timing OR simply assert 403 — timing-attack defense is by construction, not test-asserted) |
| 22 | Existing POST /test/open via bare `client` fixture | POST | — | — | — | **403** | demonstrates middleware is wired into the app |
| 23 | New `client_with_csrf` fixture round-trip | POST | (auto) | (auto) | `http://test` | 201 | fixture exercises happy path |
| 24 | CSP attached to GET / (catch-all fallback) | GET | — | — | — | 200/404 + CSP header | `response.headers["content-security-policy"]` byte-equal to AC8 value |
| 25 | CSP NOT attached to GET /api/me 401 | GET | — | — | — | 401 + **no** CSP | `"content-security-policy" not in response.headers` |
| 26 | CSP NOT attached to GET /health | GET | — | — | — | 200 + no CSP | same |
| 27 | CSP NOT attached to GET /v1/... 404 | GET | — | — | — | 404 + no CSP | same |
| 28 | CSP attached when `Accept: text/html` on unknown path | GET | — | — | — | 404 + CSP | path-driven exclusion does NOT trigger (unknown path is NOT under `/auth/`, `/api/`, `/v1/`, `/health`) |
| 29 | CSP NOT attached on `Accept: application/json` request to unknown path | GET | — | — | — | 404 + no CSP | content-negotiated: HTML-only |
| 30 | CSP header value byte-for-byte equals AC8 string | GET | — | — | — | — | exact-string equality (catches accidental whitespace / quoting drift) |
| 31 | CsrfMiddleware response carries NO CSP | POST | — | — | — | 403 + no CSP | proves middleware ordering (CSRF short-circuit bypasses SecurityHeaders) |

Coverage of `src/bff/auth/csrf.py` AND `src/bff/middleware/security_headers.py` is **≥90%** per `[tool.coverage.report] fail_under = 90` (services/bff/pyproject.toml:86). The project-wide gate is total `fail_under = 90`; per-module coverage of the new files is the epic's explicit ask (epics line 430).

[Source: epics.md#Story 1.6 lines 428–430; services/bff/pyproject.toml:82–87.]

**AC12 — Gates remain green.** No new runtime or dev dependencies. From `services/bff/`:

- `uv sync --frozen` → exit 0 (lock untouched).
- `uv run ruff check` → clean.
- `uv run ruff format --check` → clean.
- `uv run ty check` → clean.
- `uv run pytest --cov` → all 223+ prior tests + new CSRF/CSP tests pass; total coverage ≥ 90%.
- From repo root: `docker compose --profile default config` → valid; `docker compose build bff` → succeeds.

[Source: services/bff/pyproject.toml; epics.md#Story 1.6 line 430.]

## Tasks / Subtasks

- [x] **Task 1: Add `ErrorCode.CSRF_INVALID` to the enum** (AC: #7)
  - [x] In `services/bff/src/bff/core/errors.py`, after the existing `AUTH_STATE_INVALID` member at errors.py:26, add: `CSRF_INVALID = ("csrf_invalid", "CSRF token missing or invalid", 403)`. Preserve declaration order (project-specific codes are grouped per the comment at errors.py:16–19).
  - [x] In `services/bff/tests/core/test_errors.py` (extend), add one test `test_csrf_invalid_enum_shape`:
    - `assert ErrorCode.CSRF_INVALID.code == "csrf_invalid"`
    - `assert ErrorCode.CSRF_INVALID.message == "CSRF token missing or invalid"`
    - `assert ErrorCode.CSRF_INVALID.http_status == 403`
  - [x] Run `uv run pytest tests/core/test_errors.py -v` — passes.

- [x] **Task 2: Author `src/bff/auth/csrf.py`** (AC: #1, #2, #3, #4, #5, #6)
  - [x] Create `services/bff/src/bff/auth/csrf.py`. Module docstring summarizes: double-submit CSRF middleware per architecture A5 — exempts safe methods, enforces header==cookie + same-origin Origin/Referer on POST/PUT/PATCH/DELETE, emits 403 `csrf_invalid` envelope (architecture C5).
  - [x] Imports: `hmac`, `logging`, `urllib.parse.urlparse`, `typing.Final`, `starlette.middleware.base.{BaseHTTPMiddleware,RequestResponseEndpoint}`, `starlette.requests.Request`, `starlette.responses.{JSONResponse,Response}`, `bff.core.config.settings`, `bff.core.errors.ErrorCode`.
  - [x] Module-level: `logger = logging.getLogger(__name__)`. `_SAFE_METHODS: Final[frozenset[str]] = frozenset({"GET", "HEAD", "OPTIONS"})`. `_STATE_CHANGING_METHODS` is NOT defined — anything NOT in `_SAFE_METHODS` is state-changing (CONNECT/TRACE will also be guarded; correct posture).
  - [x] `class CsrfMiddleware(BaseHTTPMiddleware):` with `async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:`. Flow:
    1. If `request.method.upper() in _SAFE_METHODS` → `return await call_next(request)`.
    2. Read `cookie_value = request.cookies.get(settings.bff_csrf_cookie_name) or ""`.
    3. Read `header_value = request.headers.get("x-csrf-token") or ""` (Starlette's `headers` mapping is case-insensitive; the lookup key MUST be lowercase per Starlette docs — `request.headers.get("X-CSRF-Token")` also works, but the lowercase form is the documented one).
    4. If `not header_value` → log WARN `csrf_header_missing path=%s method=%s` (`request.url.path`, `request.method`) → `return self._reject()`.
    5. If `not cookie_value or not hmac.compare_digest(header_value.encode("utf-8"), cookie_value.encode("utf-8"))` → log WARN `csrf_token_mismatch path=%s method=%s` → `return self._reject()`.
    6. Origin check: `origin = request.headers.get("origin"); referer = request.headers.get("referer")`. Compute `expected = self._parse_origin(settings.bff_base_url)`. If `origin and origin != "null"` → compare `urlparse(origin)` triple to `expected`. Else if `referer` → compare `urlparse(referer)` triple to `expected`. Else → mismatch.
       - On mismatch: log WARN `csrf_origin_mismatch path=%s origin=%s referer_host=%s` (referer truncated to hostname per AC6) → `return self._reject()`.
    7. `return await call_next(request)`.
  - [x] Private helpers on the class:
    - `def _reject(self) -> JSONResponse:` returns `JSONResponse(status_code=ErrorCode.CSRF_INVALID.http_status, content={"errorCode": ErrorCode.CSRF_INVALID.code, "message": ErrorCode.CSRF_INVALID.message, "detail": None})`. Mirrors the shape from api/me.py:36–44 and api/auth.py:84–101 — keeps the envelope contract uniform.
    - `@staticmethod` `def _parse_origin(url: str) -> tuple[str, str, int | None]:` parses `(scheme, hostname, port)`. Use `urllib.parse.urlsplit`; if `port` is `None`, derive the default from scheme (`80` for http, `443` for https). Returning `int | None` is acceptable as long as `_origin_matches` does the same default-derivation on the incoming side.
    - `@staticmethod` `def _origin_matches(observed: str, expected: tuple[str, str, int | None]) -> bool:` — `urlsplit(observed)`, derive port default, compare triples. Returns `False` for any parse failure (defensive).
  - [x] Inline comments **only** where the WHY is non-obvious:
    - On the lowercase `"x-csrf-token"` lookup: not strictly required by Starlette (case-insensitive), but matches the project's docstring convention (and protects against a future Starlette change).
    - On `hmac.compare_digest` over `bytes`: ensures constant-time even when one side is empty — `compare_digest` is documented to NOT short-circuit on length mismatch when both inputs are `bytes`-of-equal-length, but it WILL short-circuit on different-length inputs. The length-leak is acceptable here: both values are 256-bit `secrets.token_urlsafe(32)` outputs by construction (43 chars URL-safe-base64), so a length-mismatch is a planted-attacker signal, not a token-length oracle.
  - [x] **NO `from __future__ import annotations`** — Story 1.4 / 1.5 precedent: project does not use future annotations.

- [x] **Task 3: Author `src/bff/middleware/security_headers.py`** (AC: #1, #8)
  - [x] Create `services/bff/src/bff/middleware/__init__.py` (empty).
  - [x] Create `services/bff/src/bff/middleware/security_headers.py`. Module docstring summarizes: CSP response-header middleware per architecture A8 — attaches the documented CSP header to SPA-serving (HTML) responses, skips JSON API/auth/health paths.
  - [x] Imports: `logging`, `typing.Final`, `starlette.middleware.base.{BaseHTTPMiddleware,RequestResponseEndpoint}`, `starlette.requests.Request`, `starlette.responses.Response`.
  - [x] Module-level constants:
    - `_CSP_VALUE: Final[str] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"` — EXACTLY this string (single line, single space separators, no trailing semicolon). Byte-for-byte assertion lives in test scenario #30.
    - `_API_PATH_PREFIXES: Final[tuple[str, ...]] = ("/auth/", "/api/", "/v1/", "/health")` — Trailing `/` on `/auth/` etc. matches both `/auth/login` and `/auth/`; bare `/health` is a leaf (no trailing slash because the route is exactly `/health` — see api/health.py:141). `startswith` with each prefix is the correct check.
  - [x] `class SecurityHeadersMiddleware(BaseHTTPMiddleware):` with `async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:`. Flow:
    1. `response = await call_next(request)` — always run downstream first.
    2. Compute `should_add = self._is_html_request(request) and not self._is_api_path(request.url.path)`.
    3. If `should_add` → `response.headers["Content-Security-Policy"] = _CSP_VALUE`.
    4. `return response`.
  - [x] Private static helpers:
    - `def _is_html_request(request: Request) -> bool:` returns `"text/html" in (request.headers.get("accept") or "")`. Simple substring match; `Accept: */*` does NOT match (the SPA is explicit). `Accept: text/html,application/xhtml+xml,application/xml;q=0.9` matches (substring `text/html`).
    - `def _is_api_path(path: str) -> bool:` returns `path == "/health" or any(path.startswith(p) for p in _API_PATH_PREFIXES)`.
  - [x] No logging in this middleware (it's a pure decorator). Logging is reserved for `csrf.py` (which has security-relevant decisions to record).

- [x] **Task 4: Wire middleware into `main.py`** (AC: #9, #10)
  - [x] Edit `services/bff/src/bff/main.py`:
    - Add imports after the existing `from bff.api.v1 import router as v1_router` line (main.py:11):
      ```python
      from bff.auth.csrf import CsrfMiddleware
      from bff.middleware.security_headers import SecurityHeadersMiddleware
      ```
      Ruff will sort these alphabetically within the first-party block — let `ruff format` handle final ordering; do not pre-sort manually.
    - Between the CORS `if settings.cors_enabled:` block (ending main.py:46) AND the `app.add_exception_handler(AppException, ...)` line (main.py:48), add:
      ```python
      app.add_middleware(SecurityHeadersMiddleware)
      app.add_middleware(CsrfMiddleware)
      ```
      — order matters per AC9 (LIFO onion).
  - [x] Run `uv run ruff format` then `uv run ruff check` — clean.
  - [x] Run `uv run ty check` — clean. (`BaseHTTPMiddleware` subclasses are typed end-to-end; no `# ty: ignore` should be needed. If `app.add_middleware()` complains via the `CORSMiddleware` `# ty: ignore[invalid-argument-type]` precedent at main.py:39 — match the comment and ignore tag on the new lines.)

- [x] **Task 5: Author `tests/auth/test_csrf.py`** (AC: #11 scenarios 1–23, 31)
  - [x] Create `services/bff/tests/auth/test_csrf.py`.
  - [x] Imports: `pytest`, `httpx.AsyncClient`, `bff.core.config.settings`, `bff.core.errors.ErrorCode`.
  - [x] Add a module-level `_CSRF_VALUE = "test-csrf-secret-43chars-xxxxxxxxxxxxxxxxxxxx"` (43 chars to mirror `secrets.token_urlsafe(32)`'s real length — defends against accidental length-leak regressions in `_constant_time_eq`).
  - [x] Add a `client_with_csrf` fixture in `tests/conftest.py` (extend; do NOT duplicate):
    ```python
    @pytest.fixture(name="client_with_csrf")
    async def client_with_csrf_fixture(session):
        async def _override():
            yield session
        app.dependency_overrides[get_session] = _override
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"bff_csrf": "test-csrf-secret"},
            headers={"X-CSRF-Token": "test-csrf-secret", "Origin": "http://test"},
        ) as c:
            yield c
        app.dependency_overrides.clear()
    ```
    **Important:** `base_url="http://test"` matches what the existing `client` fixture uses; `bff_base_url` defaults to `http://localhost:8000` per config.py:80, so the `client_with_csrf` fixture must ALSO `monkeypatch.setattr(settings, "bff_base_url", "http://test")` OR the test must do so. **Recommended:** make the fixture depend on a `monkeypatch` fixture and set `bff_base_url="http://test"` inside it. Pytest's `monkeypatch` is function-scoped, so the setattr unwinds between tests.
  - [x] For each scenario in the AC11 matrix rows 1–23 and 31, write one test function. Group by behavior (safe-methods, header-missing, mismatch, origin-check) using `@pytest.mark.parametrize` where shape matches.
  - [x] Use the existing `POST /test/open` stub (tests/conftest.py:44) as the downstream target. The stub returns 201 with `{"value": payload.value}` — test happy paths assert `response.status_code == 201` AND `response.json() == {"value": "..."}`.
  - [x] For caplog assertions (`csrf_header_missing`, `csrf_token_mismatch`, `csrf_origin_mismatch`), use the pytest `caplog` fixture: `caplog.set_level(logging.WARNING, logger="bff.auth.csrf")` then assert `any("csrf_header_missing" in r.message for r in caplog.records)`. Story 1.5's tests use `caplog` in test_auth.py — same pattern.
  - [x] **Scenario 22 (existing POST /test/open via bare `client`)**: use the existing `client` fixture (no `client_with_csrf`). Assert 403 + `csrf_invalid` envelope. This is the "middleware is wired" check.
  - [x] **Scenario 23 (round-trip via `client_with_csrf`)**: assert 201 + correct body. Inverse of #22.
  - [x] **Scenario 31 (CSRF reject carries no CSP)**: GET `client.post("/test/open")` without CSRF cookie/header. Assert 403 AND `"content-security-policy" not in response.headers`. Proves SecurityHeaders is INNER to CSRF in the middleware onion.

- [x] **Task 6: Author `tests/middleware/test_security_headers.py`** (AC: #11 scenarios 24–30)
  - [x] Create `services/bff/tests/middleware/__init__.py` (empty).
  - [x] Create `services/bff/tests/middleware/test_security_headers.py`.
  - [x] Imports: `pytest`, `httpx.AsyncClient`.
  - [x] Module-level constant `_EXPECTED_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                                                "base-uri 'self'; form-action 'self'")` — same byte-string as `_CSP_VALUE`.
  - [x] Tests per scenario rows 24–30:
    - **Scenario 24 (CSP on catch-all 404 with `Accept: text/html`)**: `client.get("/some-unknown-path", headers={"Accept": "text/html"})`. Assert `response.headers["content-security-policy"] == _EXPECTED_CSP`. **Caveat:** with no static SPA mount yet (Story 1.10 lands that), the route emits Starlette's default 404 envelope. The CSP header still attaches because path-prefix is not in `_API_PATH_PREFIXES`. **Note:** D16 (unreviewed 404 envelope shape) is separately deferred; this story does NOT fix the envelope, only adds the CSP header.
    - **Scenario 25 (no CSP on /api/me 401)**: `client.get("/api/me")`. Assert `"content-security-policy" not in response.headers`. (`/api/me` returns 401 without any cookie — fast path.)
    - **Scenario 26 (no CSP on /health)**: `client.get("/health")`. Same assertion. (`/health` may hit OIDC discovery and return 503 in test — assert on header absence regardless of status.)
    - **Scenario 27 (no CSP on /v1/ 404)**: `client.get("/v1/nope")`. Same.
    - **Scenario 28 (CSP attached on Accept: text/html unknown path)**: combined with #24 — split into a dedicated test if clearer.
    - **Scenario 29 (no CSP on Accept: application/json unknown path)**: `client.get("/random", headers={"Accept": "application/json"})`. Assert `"content-security-policy" not in response.headers`.
    - **Scenario 30 (byte-for-byte CSP value)**: pull `response.headers["content-security-policy"]` from any HTML response, compare exact equality with `_EXPECTED_CSP`.
  - [x] **Important:** these tests use the standard `client` fixture (no CSRF setup needed — all GETs). The `client` fixture's `app.dependency_overrides[get_session] = _override` is irrelevant for GET on unknown paths but does no harm.

- [x] **Task 7: Update `tests/conftest.py` for the new `client_with_csrf` fixture** (AC: #10, #11 row 23)
  - [x] Edit `services/bff/tests/conftest.py`:
    - Add the `client_with_csrf` fixture per Task 5's spec.
    - Add `monkeypatch.setattr(settings, "bff_base_url", "http://test")` inside the fixture's setup so AC3's origin check matches the test client's `base_url`. **Important:** `monkeypatch` is function-scoped; auto-includes in pytest. The fixture must accept `monkeypatch: pytest.MonkeyPatch` as a parameter.
  - [x] **Do NOT migrate existing tests.** The existing `POST /test/open` test in `tests/api/test_cors.py` is part of the CORS test suite and uses the bare `client` fixture. Once CSRF middleware lands, that test SHOULD fail with 403 — and Task 5's scenario #22 explicitly exercises this. **Action:** the existing test in `test_cors.py` either (a) gets retired (covered by scenario #22) OR (b) migrates to use `client_with_csrf`. **Recommended:** migrate the CORS test to `client_with_csrf` so CORS-specific behavior is still exercised on a state-changing request. See Task 8.

- [x] **Task 8: Reconcile `tests/api/test_cors.py` with active CSRF middleware** (AC: #10)
  - [x] Open `services/bff/tests/api/test_cors.py`.
  - [x] Identify each test that issues a `client.post(...)` / `client.put(...)` / `client.patch(...)` / `client.delete(...)` AND verify it still passes under active CSRF. Two options per test:
    1. Test exercises CORS preflight / origin policy ONLY → switch to `client_with_csrf` so the request has the CSRF cookie + header by default.
    2. Test is asserting behavior orthogonal to CSRF (e.g., preflight `OPTIONS` request) → leave the bare `client` (OPTIONS is a safe method per AC2, so CSRF passes through).
  - [x] Run `uv run pytest tests/api/test_cors.py -v` — clean pass.

- [x] **Task 9: Run the full BFF gate matrix** (AC: #12)
  - [x] From `services/bff/`:
    - `uv sync --frozen` → exit 0 (no dep changes).
    - `uv run ruff check` → clean (if I001 import-order trips, `uv run ruff check --fix`).
    - `uv run ruff format --check` → clean (if format trips, `uv run ruff format`).
    - `uv run ty check` → clean.
    - `uv run pytest --cov` → all 223+ prior tests + new CSRF/CSP tests pass; total coverage ≥ 90%.
    - `uv run pytest --cov=src/bff/auth/csrf --cov=src/bff/middleware/security_headers -v` → per-module coverage ≥ 90% on each.
  - [x] From repo root:
    - `docker compose --profile default config` → valid.
    - `docker compose build bff` → succeeds.
  - [x] Capture command output excerpts in **Debug Log References**.

- [x] **Task 10: Update sprint-status + deferred-work**
  - [x] On story start: flip `_bmad-output/implementation-artifacts/sprint-status.yaml` development_status `1-6-bff-csrf-middleware-csp-header: ready-for-dev` → `in-progress`. Bump `last_updated`.
  - [x] On story complete (before `code-review`): flip to `review`. Bump `last_updated`.
  - [x] If any new defects surface during implementation, append them as D45+ in `deferred-work.md` with severity / owner-story / rationale.
  - [x] **D44** (module-level `_session_service` singleton) is explicitly deferred AGAIN — do NOT refactor in this story.

## Dev Notes

### What this story is — and is not

**This story adds the BFF's CSRF middleware (double-submit cookie + `X-CSRF-Token` header + Origin/Referer check per architecture A5) AND the SPA CSP header middleware (architecture A8). It introduces the `ErrorCode.CSRF_INVALID` enum member. It wires both middlewares into `main.py` with documented LIFO ordering.**

**Explicitly NOT in scope (each is a downstream story OR a previous story's responsibility):**

- **No `/auth/logout` endpoint.** Story 1.7 owns it. Story 1.7's AC6 explicitly DEPENDS on this story's middleware to enforce the `403 csrf_invalid` response on missing/mismatched `X-CSRF-Token` for `POST /auth/logout`. Once this story merges, Story 1.7's `Scenario 15` (currently `@pytest.mark.skipif`) auto-unskips. See "Cross-story dependency" below.
- **No CSRF cookie SET logic.** Story 1.5 (done) already sets the `bff_csrf` cookie at `/auth/callback` time with the correct attributes (non-HttpOnly, SameSite=Lax, Path=/, Secure per env). See api/auth.py:279–286. This story only READS the cookie.
- **No SPA changes.** Story 1.9 (done) already has `csrfInterceptor` reading the cookie and setting `X-CSRF-Token`. This story makes the BFF enforce that the SPA's interceptor is doing its job.
- **No CSP nonce injection.** Architecture A8 explicitly chose `'unsafe-inline'` on styles "to accommodate Tailwind without nonce-injection complexity." Do NOT add a nonce; do NOT swap to `'strict-dynamic'`.
- **No `Content-Security-Policy-Report-Only` header.** Out of scope. The AC's CSP string is the enforced one.
- **No SPA static mount.** Story 1.10 (`SPA LoginView + TopChrome`) and a later story (likely Epic 5 polish — Story 5.4 / final docker compose smoke) will mount `spa/dist/spa/browser` at `/`. Until then, the only HTML the BFF serves is the catch-all 404 path (Story 1.3 / D16 — Starlette default envelope). The CSP middleware works against the catch-all by Accept-header content negotiation.
- **No `BookService`, `BooksService`, `/v1/books` routes** (Epic 2).
- **No `ResourceServerClient` (BFF → RS).** Story 3.5.
- **No CSRF token rotation** beyond Story 1.5's session-lifecycle semantics (each login mints a fresh `csrf_secret`). This story does NOT rotate the secret per-request.
- **No origin allowlist beyond `BFF_BASE_URL`.** Same-origin is the entire policy — no `BFF_ALLOWED_ORIGINS` env var, no multi-origin support. Architecture F3 (same-origin SPA serving) is the entire reason.

### Cross-story dependency (CRITICAL — read before merging)

**Story 1.7 (`POST /auth/logout`) is `ready-for-dev` and has been written assuming this story (1.6) lands first.** Story 1.7's AC6 says verbatim: "this response is produced by the CSRF middleware introduced in Story 1.6 (`src/bff/auth/csrf.py`), NOT by the `/auth/logout` handler itself." Story 1.7's Scenario 15 is `@pytest.mark.skipif(not _csrf_middleware_installed(), ...)`.

**Recommended merge order:** 1.6 → 1.7. If 1.6 lands first:

1. Story 1.7's Scenario 15 auto-unskips on next test run.
2. Story 1.7's handler (when implemented) does NOT need to add CSRF checks; the middleware intercepts the POST and returns 403 before the handler runs.
3. Story 1.7's test fixtures will need to send the CSRF cookie + header on the logout POST (the test author already accounts for this — see Story 1.7's `_seed_session` helper spec).

**If 1.6 lands AFTER 1.7:** Story 1.7's Scenario 15 is unskipped retroactively. No code changes needed in 1.7. The only operational note: between 1.7's merge and 1.6's merge, the BFF would accept logout without a CSRF check — a window of unprotected state-changing requests. Both stories are in the same epic (Epic 1) and slotted before any production cutover.

### Cookie & header contract (matches Story 1.5's set semantics)

| Attribute | Set by | Value | Read by | Constraint |
|---|---|---|---|---|
| `bff_csrf` cookie | Story 1.5 at `/auth/callback` (api/auth.py:279–286) | `sessions.csrf_secret` (43-char `secrets.token_urlsafe(32)` output) | This story's middleware | Non-HttpOnly (SPA reads it); SameSite=Lax; Path=/; Secure per env |
| `X-CSRF-Token` header | SPA's `csrfInterceptor` (Story 1.9) | The cookie value | This story's middleware | Sent on POST/PUT/PATCH/DELETE; absent on GET/HEAD/OPTIONS |
| `Origin` header | Browser (automatic) | Request origin (scheme + host + port) | This story's middleware | RFC 6454 ASCII-only; may be `"null"` for sandboxed contexts |
| `Referer` header | Browser (automatic, unless suppressed) | Full URL of the source page | This story's middleware | May be absent under strict `Referrer-Policy`; fallback only |

**Why the middleware does NOT also set or refresh the CSRF cookie.** Architecture A5 ("Double-submit cookie + custom header + Origin/Referer check") is read-only at the middleware layer. The cookie is set on login (Story 1.5) and cleared on logout (Story 1.7). A request-scoped middleware that rotated the cookie per-request would either (a) break the double-submit invariant (the SPA's cached cookie wouldn't match the new value mid-flight) or (b) require coordination with the SPA's interceptor. Neither is needed for double-submit correctness.

### Middleware ordering (Starlette LIFO onion — non-obvious)

Starlette/FastAPI middleware stacks process requests in **reverse-add order on the way in** and **add-order on the way out**. From `main.py` (after this story):

```python
if settings.cors_enabled:
    app.add_middleware(CORSMiddleware, ...)        # 1st added (outermost)
app.add_middleware(SecurityHeadersMiddleware)       # 2nd added
app.add_middleware(CsrfMiddleware)                  # 3rd added (innermost)
```

**Onion (request path):** `client → CORS → CSRF → SecurityHeaders → router_handler`.

**Onion (response path):** `router_handler → SecurityHeaders → CSRF → CORS → client`.

**Implications:**

- CSRF runs BEFORE the router. A 403 from CSRF short-circuits and never reaches the handler.
- SecurityHeaders runs AFTER the router (on the way out) ONLY when the request flowed through CSRF without short-circuit. A CSRF-403 bypasses SecurityHeaders → no CSP on the 403. **Correct** (CSP is for HTML, not JSON envelopes).
- If a future story adds an authn middleware that needs to short-circuit BEFORE CSRF (e.g., a global session-lookup), add it AFTER `CsrfMiddleware` (`app.add_middleware(SessionMiddleware)` later in main.py) so it becomes the innermost layer.
- CORS being outermost means CSRF rejection responses still get CORS headers when `cors_enabled=True`. The current config defaults `cors_enabled=False`, so this is moot in default deployment.

**Why SecurityHeaders is INSIDE CSRF (not parallel or outside):** CSP is a response-decorator. Putting it inside means it sees only requests that pass CSRF — which are exactly the requests that get downstream responses. If SecurityHeaders were OUTSIDE CSRF (added LAST), it would also decorate the 403 CSRF rejection response with CSP, which is wrong (the 403 is JSON; CSP belongs on HTML).

### Same-origin check — exact algorithm

```python
def _parse_origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, hostname, port). Defaults port from scheme when omitted."""
    parts = urlsplit(url)
    scheme = parts.scheme
    hostname = parts.hostname or ""
    port = parts.port
    if port is None:
        port = {"http": 80, "https": 443}.get(scheme)
    return (scheme, hostname, port)
```

**Tests that exercise the parser directly** (Task 5, scenarios 13–20):

- `http://localhost:8000` → `("http", "localhost", 8000)`.
- `http://localhost` → `("http", "localhost", 80)` (HTTP default).
- `https://localhost` → `("https", "localhost", 443)`.
- `null` (Origin special value) → caller must skip this and fall back to Referer.

**Why scheme is checked too:** an HTTP origin POSTing to an HTTPS BFF (or vice-versa) is a mixed-content scenario the browser would block, but defense-in-depth in the BFF catches misconfiguration earlier.

### CSP value — exact string + rationale

Per architecture A8 (line 354) AND epics line 425, the header VALUE is exactly (no leading/trailing whitespace; spaces are single ASCII space; semicolons followed by single space):

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

Directive rationale (decided in architecture, NOT this story — do NOT change):

- `default-src 'self'` — fallback for unlisted resource types.
- `script-src 'self'` — same-origin JS only. No inline scripts. Tailwind generates CSS at build, no inline `<script>`s in Angular's prod output.
- `style-src 'self' 'unsafe-inline'` — Tailwind v4 needs inline styles for some utilities; nonce injection rejected by A8 as over-engineering.
- `img-src 'self' data:` — Angular's icon pipeline embeds some `data:` URLs.
- `connect-src 'self'` — XHR/fetch to same-origin only (BFF↔SPA is same-origin per F3).
- `frame-ancestors 'none'` — anti-clickjacking. Note: this REPLACES `X-Frame-Options: DENY` (modern browsers prefer the CSP directive; legacy IE not supported per AINE PRD context).
- `base-uri 'self'` — prevents `<base href>` injection from redirecting relative URLs to evil hosts.
- `form-action 'self'` — restricts `<form action>` to same-origin.

**Header name capitalization:** Per RFC 7230 §3.2, header names are case-insensitive. The middleware sets `response.headers["Content-Security-Policy"] = ...`; Starlette normalizes-on-read so tests reading `response.headers["content-security-policy"]` see the same value.

### Architecture-mandated contract details

#### HTTP status code (architecture §Format Patterns line 684 + C5 line 408)

CSRF rejection returns **403 No Content**, body = `{"errorCode": "csrf_invalid", "message": "CSRF token missing or invalid", "detail": null}`. Not 401, not 400 — `403` is the documented mapping in architecture line 684.

#### Logging conventions (architecture lines 781–788)

- INFO: none in this middleware (security-sensitive WARN-or-nothing).
- WARN on each rejection: `csrf_header_missing`, `csrf_token_mismatch`, `csrf_origin_mismatch` — three distinct classifiers so operators can grep failure reasons.
- ERROR: none — middleware does not throw; any internal exception (e.g., `urlsplit` raising on malformed URL — unlikely) propagates to FastAPI's default handler.
- **Never** log the cookie value, the header value, or any token material. Origin header values are RFC 6454 ASCII-only and have no PII; Referer hostnames are similarly safe (the path query string is where PII would live — TRUNCATE Referer to `urlparse(referer).hostname` before logging per AC6).
- Path is safe to log per architecture lines 783–788 (it's request metadata, not body content).

#### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules" lines 797–815)

- **Python files:** `snake_case.py`. New files: `csrf.py`, `security_headers.py`, `__init__.py` (in new `middleware/` subpackage).
- **Classes:** `PascalCase`. `CsrfMiddleware`, `SecurityHeadersMiddleware`.
- **Functions / methods:** `snake_case` — `_reject`, `_parse_origin`, `_origin_matches`, `_is_html_request`, `_is_api_path`.
- **Wire values:** `lower_snake_case` — `csrf_invalid` (architecture line 408).
- **Tests mirror source paths.** `src/bff/auth/csrf.py` → `tests/auth/test_csrf.py`. `src/bff/middleware/security_headers.py` → `tests/middleware/test_security_headers.py`.
- **Use `ErrorCode` for every non-success response.** The middleware builds its 403 body via `ErrorCode.CSRF_INVALID.code` / `.message` — same pattern as api/me.py:36–44.
- **No `from __future__ import annotations`** — project precedent (Stories 1.3–1.5 confirmed).

### Previous story intelligence (from 1.1–1.5, 1.8, 1.9)

**Patterns established that this story must follow:**

- **`UTC` datetime everywhere.** Not applicable here — middleware does no time math.
- **`secrets.token_urlsafe(32)` for opaque ids — but NOT in this story.** This story consumes existing CSRF secret values; it does NOT mint new ones.
- **`logger = logging.getLogger(__name__)`** at module top. Never `print`. WARN for security-rejection paths.
- **Module-level singletons are OK for stateless objects** but NOT for middleware classes — Starlette instantiates one per app, and `app.add_middleware(CsrfMiddleware)` is the documented idiom.
- **`response.set_cookie(..., value="", max_age=0, ...)`, NOT `response.delete_cookie(...)`.** Story 1.5 Review Findings P3 established this. This story does NOT clear or rotate cookies, so the precedent is informational only.
- **`from bff.models import entities` then `entities.Session`.** Not applicable — middleware does not touch the DB.
- **JSONResponse with manual envelope construction** is the idiom when the response carries side-effects (cookies, headers). For pure-error responses with no side-effects (this story's 403), `JSONResponse(status_code=403, content={...})` is equivalent to raising `AppException(ErrorCode.CSRF_INVALID)` and letting the global handler render it. **Use the direct `JSONResponse`** — middleware short-circuit cannot raise `AppException` cleanly (FastAPI's exception handlers run inside the router; raising from middleware bypasses them and triggers Starlette's default 500). See `_session_expired_response` at api/me.py:36–44 for the exact shape pattern.
- **Synthetic IdP fixture pattern.** Not exercised here (no IdP traffic in this story).
- **Coverage gate is total 90%** AND per-module ≥90% for the new files (epic-mandated).
- **`tests/conftest.py:34–48` has stub routes** (`GET /test/open`, `POST /test/open`) intentionally welded onto the live app for cross-cutting middleware tests. D17 deferred this; it's the right vehicle for THIS story's tests too.

**Deferred items relevant to this story:**

- **D16 (404/405 don't follow envelope contract)** — orthogonal. This story's CSP middleware adds headers; it does NOT fix the envelope. If the 404 envelope changes in a future story, the CSP middleware's path-prefix logic still applies.
- **D29 (`CORSMiddleware` typed with `# ty: ignore`)** — likely applies to the new `app.add_middleware(...)` calls. Match the precedent if `ty` complains.
- **D33 closed by 1.5** — `safe_return_to` validation lives in `keycloak_cookie_session.py`. Not exercised by this story.
- **D44 (module-level `_session_service` singleton)** — still deferred. Do NOT refactor in this story.

**No new deferred items expected** unless implementation surfaces a new race condition or edge case (e.g., CSRF middleware interaction with a future SPA static-file mount in Story 1.10).

### Anti-patterns to avoid

- **Do NOT add `from __future__ import annotations`.**
- **Do NOT use `python3`.** Project convention (`CLAUDE.md`): always `python`. **All gate commands in Tasks 9 use `uv run ...` which already invokes Python 3.14 from the lock — `python3` would not be reached anyway, but if hand-running a script (e.g., the customization resolver), use `python`.**
- **Do NOT raise `AppException(ErrorCode.CSRF_INVALID)` from the middleware.** The `app_exception_handler` (errors.py:47–54) is registered as a FastAPI exception handler — it runs INSIDE the router, not at middleware scope. Raising from middleware lands in Starlette's default 500 handler. **Return `JSONResponse(...)` directly.**
- **Do NOT use `request.scope["headers"]` directly.** Use `request.headers.get("x-csrf-token")` — the high-level API normalizes case.
- **Do NOT use the equality operator (`==`) to compare the header and cookie.** Use `hmac.compare_digest(...)` — constant-time. The non-constant-time `==` would leak timing oracles for the 256-bit CSRF secret.
- **Do NOT log the cookie or header value, even at DEBUG.** Architecture line 787 is explicit.
- **Do NOT add a `nonce-…` directive to the CSP.** Architecture A8 explicitly rejected nonce injection.
- **Do NOT serve `Content-Security-Policy-Report-Only` instead of `Content-Security-Policy`.** The AC string is enforced policy.
- **Do NOT add a CSP-report endpoint.** Out of scope.
- **Do NOT attach CSP to JSON API responses.** Path prefix exclusion (`/auth/`, `/api/`, `/v1/`, `/health`) is the gate; the Accept-header check is defense-in-depth.
- **Do NOT skip the Origin/Referer check.** Architecture A5 mandates it ("defense in depth"). Even with header==cookie match, a CSRF token leaked via XSS would otherwise be replayable from any origin.
- **Do NOT add `Vary: Origin` or `Vary: Referer`.** No caching layer downstream; the header would be decorative.
- **Do NOT skip case-insensitive header lookup.** Starlette is case-insensitive, but a regression to `request.headers.get("X-CSRF-Token")` and another developer adding `request.headers["x-csrf-token"]` next year creates inconsistency. **Use lowercase keys consistently** (project lint: ruff doesn't enforce this, but match the existing pattern at api/me.py / api/auth.py where headers are read via lowercase keys when explicit).
- **Do NOT exempt `/auth/login` from CSRF.** `/auth/login` is GET — already exempt via AC2 (safe methods). If a future story adds `POST /auth/login` (it won't — see Story 1.5 done), CSRF MUST apply.
- **Do NOT add an `enable_csrf` env var.** Architecture A5 mandates CSRF unconditionally; a kill-switch invites accidental disable in prod.
- **Do NOT skip the CSP middleware for /docs or /redoc.** `/docs` and `/redoc` serve HTML (Swagger UI). They're NOT in the path exclusion list — CSP should attach. **However:** Swagger UI uses inline scripts and external CDNs (`cdn.jsdelivr.net`) by default; CSP with `script-src 'self'` will break it visually. **Decision (this story):** accept that `/docs` is broken under CSP. The OpenAPI JSON at `/openapi.json` is JSON (not HTML) so it's unaffected. `/docs` is a developer tool, not a production surface — the operational tradeoff is documented in the security review (Story 5.2). If a future story needs `/docs` working under CSP, it adds a CSP exemption for that specific path OR loosens to `script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net` — both are out of scope here. **Tests should NOT assert CSP behavior on `/docs`** (avoid coupling to FastAPI's internals).

### Latest tech information

- **Starlette `BaseHTTPMiddleware`** is the documented base class for response-decorating middleware. It runs in a streaming response wrapper — for response-header writes, it's the right tool. (The alternative `ASGIApp`-based pattern is heavier and only needed for streaming-body manipulation.)
- **`hmac.compare_digest`** — stdlib (Python 3.14+ unchanged). Constant-time. Accepts `bytes` OR `str`; documented constant-time behavior is for **equal-length** inputs. For different-length inputs, returns `False` quickly (acceptable; the leaked length signal is one bit and the secret is 256 bits, so no practical exploit).
- **`urllib.parse.urlsplit`** — stdlib. Faster than `urlparse` and returns the same fields; the difference is that `urlsplit` does NOT separate `params` from `path` (we don't care about either).
- **FastAPI 0.135.1 + Starlette 0.40+** — `app.add_middleware(...)` is the supported API. The `# ty: ignore[invalid-argument-type]` on the CORS install (main.py:39) reflects that `add_middleware`'s signature is `(*args, **kwargs)` — typed-language tooling can't infer the per-middleware constructor args. Match the precedent if `ty check` complains; otherwise omit.
- **No new deps.** `hmac`, `urllib.parse`, `logging`, `typing.Final` are all stdlib. `starlette.middleware.base.BaseHTTPMiddleware` is already imported transitively via FastAPI.

### Git intelligence (recent commits)

```
2c2a86c feat: implement story 1.5
6550fa4 feat: implement story 1.4
ba784f8 Merge branch 'story-1-3'
295ed48 feat: 1-3 scaffold bffe
60aa25b feat: completed bff scaffolding
```

- Story 1.5 (the immediately-prior BFF story) just landed on `main` (2c2a86c). The CSRF cookie is set there at `/auth/callback` (api/auth.py:279–286). This story enforces it.
- Story 1.7 (BFF logout) is `ready-for-dev` on disk at `_bmad-output/implementation-artifacts/1-7-bff-logout-endpoint-revoke-end-session-degrade-honestly.md` — see Cross-story dependency above.
- Stories 1.8 (SPA scaffold), 1.9 (SPA AuthService + interceptors), 1.4 (sessions table) are merged. The SPA's `csrfInterceptor` already sends `X-CSRF-Token` matching the cookie on state-changing requests; this story makes the BFF enforce it.
- Branch convention from prior stories: `story-1-6`. Create from `main`.
- No conflicts expected: stories 1.10–1.13 are downstream (backlog), Story 1.7 touches `auth.py` / `keycloak_cookie_session.py` / `session_service.py` / `synthetic_idp.py` but NOT `csrf.py` / `security_headers.py` / `main.py:31–53`'s middleware block. If 1.7 lands first, this story will need to rebase its `main.py` insertion point but the diff is mechanical (2 lines added between existing landmarks).

### Project Structure Notes

**New files (all under `services/bff/`):**

- `src/bff/auth/csrf.py` — CSRF middleware (architecture C-C Mapping line 1192 specifies this exact path).
- `src/bff/middleware/__init__.py` — empty package marker.
- `src/bff/middleware/security_headers.py` — CSP middleware. **Architecture discrepancy:** architecture line 1193 places this in `src/bff/app.py`; the actual entry point is `src/bff/main.py` (Story 1.3 precedent). Putting it in its own module under `middleware/` keeps `main.py` focused on wiring and isolates the security-header logic. This matches the spirit of architecture's "one router file per resource family" pattern (architecture line 897) — middleware gets its own home.
- `tests/auth/test_csrf.py` — middleware route tests (~30 scenarios).
- `tests/middleware/__init__.py` — empty.
- `tests/middleware/test_security_headers.py` — CSP route tests (~7 scenarios).

**Modified files (all under `services/bff/`):**

- `src/bff/core/errors.py` — add `CSRF_INVALID` enum member (1 line).
- `src/bff/main.py` — add 2 imports + 2 `app.add_middleware(...)` calls (~4 lines).
- `tests/conftest.py` — add `client_with_csrf` fixture (~18 lines).
- `tests/api/test_cors.py` — migrate POST tests to `client_with_csrf` OR retire (Task 8).
- `tests/core/test_errors.py` — add `test_csrf_invalid_enum_shape` (1 test).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status flips + `last_updated`.

**Untouched (verified):**

- `services/bff/pyproject.toml` / `uv.lock` — no dep changes.
- `services/bff/src/bff/api/{auth.py, me.py, health.py, v1/}` — unchanged.
- `services/bff/src/bff/auth/{keycloak_cookie_session.py, pkce.py}` — unchanged.
- `services/bff/src/bff/services/session_service.py` — unchanged.
- `services/bff/src/bff/models/entities/{session.py, auth_state.py}` — unchanged.
- `services/bff/alembic/` — no new migration (no schema changes).
- `compose/`, `keycloak/`, `docker-compose.yml`, `keycloak/realm-bmad-books.json` — unchanged.
- `spa/`, `e2e/` — not in scope. The SPA's `csrfInterceptor` was authored in Story 1.9; it already sends the header.
- `services/resource-server/` — does not exist yet (Epic 3).

**Naming-pattern verification:**

- New python module names are `snake_case.py` ✓.
- New class names are `PascalCase` (`CsrfMiddleware`, `SecurityHeadersMiddleware`) ✓.
- New enum member is `SCREAMING_SNAKE_CASE` (`CSRF_INVALID`) ✓.
- New wire value is `lower_snake_case` (`csrf_invalid`) ✓.
- Tests mirror source paths ✓.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.6` lines 396–430] — canonical story spec (Given/When/Then ACs, CSP exact value, test enumeration).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security A5` line 351] — Double-submit cookie + custom header + Origin/Referer check.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security A8` line 354] — CSP exact directive list + `'unsafe-inline'` style rationale.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns C5` line 408] — `CSRF_INVALID = "csrf_invalid"` (HTTP 403) ErrorCode contract.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Format Patterns` line 684] — 403 → `csrf_invalid` mapping.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Cross-Cutting Concerns Mapping` lines 1192–1193] — file-location contract: `src/bff/auth/csrf.py` AND `src/bff/app.py` (entry-point discrepancy resolved in favor of `src/bff/middleware/security_headers.py` + wiring in `main.py`).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` line 913] — `csrf.py` colocated with `keycloak_cookie_session.py` and `pkce.py` in `src/bff/auth/`.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details "BFF routing precedence"` lines 1343–1349] — path-prefix list for CSP exclusion (`/auth/*`, `/api/*`, `/v1/*`, `/health`).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Logging conventions` lines 781–788] — WARN classifiers, no PII / token material in logs.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Requirements to Structure Mapping`] — AR11 (CSRF strategy), AR14 (CSP header), AR17 (`CSRF_INVALID` ErrorCode).
- [Source: `_bmad-output/planning-artifacts/PRD.md#NFR12`] — security posture deliverable that this story partially fulfills.
- [Source: `_bmad-output/planning-artifacts/PRD.md#AR11, AR14, AR17` lines 65, 68, 74] — same.
- [Source: `_bmad-output/implementation-artifacts/1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md`] — sets the `bff_csrf` cookie at callback time; established the `_session_expired_response` shape this story's `_reject` mirrors; Review Findings P3 (cookie-clear attribute mismatch) is informational only here.
- [Source: `_bmad-output/implementation-artifacts/1-7-bff-logout-endpoint-revoke-end-session-degrade-honestly.md`] — depends on this story's middleware for AC6 (logout CSRF enforcement); Scenario 15 is `@pytest.mark.skipif` until this story merges.
- [Source: `services/bff/src/bff/main.py:31–53`] — middleware install point.
- [Source: `services/bff/src/bff/api/auth.py:279–286`] — Story 1.5 sets the `bff_csrf` cookie with non-HttpOnly + SameSite=Lax + Path=/ + Secure-per-env.
- [Source: `services/bff/src/bff/api/me.py:36–44`] — `_session_expired_response` is the shape pattern for the new `_reject` helper.
- [Source: `services/bff/src/bff/core/errors.py:9–26`] — `ErrorCode` enum surface; AUTH_STATE_INVALID at line 26 is the new neighbor for CSRF_INVALID.
- [Source: `services/bff/src/bff/core/config.py:80, 93`] — `bff_base_url` (origin check anchor), `bff_csrf_cookie_name` (cookie lookup key).
- [Source: `services/bff/tests/conftest.py:34–48, 77–106`] — stub router + `client` / `client_no_redirects` fixtures; `client_with_csrf` extends the pattern.
- [Source: `services/bff/tests/api/test_cors.py`] — existing POST tests that need migration to `client_with_csrf` (Task 8).
- [Source: `services/bff/tests/core/test_errors.py`] — extend with `test_csrf_invalid_enum_shape`.
- [Source: `services/bff/pyproject.toml:82–87`] — coverage gates (90% total, per-module enforced via the epic AC).
- [Source: RFC 6265bis] — `Set-Cookie` attribute mirroring on clear (informational; this story does not clear cookies).
- [Source: RFC 6454] — Origin header format and `null` semantics.
- [Source: RFC 7230 §3.2] — header name case-insensitivity.
- [Source: W3C CSP Level 3] — `frame-ancestors`, `base-uri`, `form-action` directive semantics.
- [Source: `CLAUDE.md`] — `python` (not `python3`).
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — Python 3.14 + FastAPI + SQLModel + uv + OTEL archetype mandate.
- [Source: `[[project-bmad-books-scope]]` — user memory] — accessibility and responsive design out of scope (no a11y assertions in tests).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Test-first cycle (Task 1):**

```
$ uv run pytest tests/core/test_errors.py::test_csrf_invalid_enum_shape -v
tests/core/test_errors.py::test_csrf_invalid_enum_shape FAILED
AttributeError: type object 'ErrorCode' has no attribute 'CSRF_INVALID'

# enum member added →

$ uv run pytest tests/core/test_errors.py -v
13 passed in 0.02s
```

**ty check on new wiring (Task 4):**

```
$ uv run ty check src/
Found 2 diagnostics — Expected `_MiddlewareFactory[(...)]`, found `<class 'CsrfMiddleware'>`
# matched the existing D29 precedent at main.py:39 (CORSMiddleware) with the
# same `# ty: ignore[invalid-argument-type]` trailing comment →
$ uv run ty check src/
All checks passed!
```

**Test-suite runs (Tasks 5–8):**

```
$ uv run pytest tests/auth/test_csrf.py -v
24 passed in 0.12s
$ uv run pytest tests/middleware/test_security_headers.py -v
8 passed in 0.05s
$ uv run pytest tests/api/test_cors.py -v
2 passed in 0.02s   # CORS suite uses GET/OPTIONS only — no migration needed
```

**Regression seen and fixed:** `test_validation_error_via_http` in
`tests/core/test_errors.py` previously POST'd `/test/open` via the bare
`client` fixture to exercise the 422 path. With CSRF now active, the bare
POST is intercepted at 403 before reaching the validator. Migrated the
test to use `client_with_csrf` so the request reaches the validator. No
other existing test exercised a POST/PUT/PATCH/DELETE through the bare
`client`.

**Full gate matrix (Task 9):**

```
$ uv sync --frozen                                 # Checked 65 packages — no dep changes
$ uv run ruff check                                # All checks passed!
$ uv run ruff format --check                       # 63 files already formatted
$ uv run ty check                                  # All checks passed!
$ uv run pytest --cov                              # 264 passed; total coverage 97.35% (gate ≥90%)
$ docker compose --profile default config          # valid (with .env staged from .env.example)
$ docker compose build bff                         # Image bmad_books-bff Built
```

**Per-module coverage of new code (Task 9 explicit ask):**

```
src/bff/auth/csrf.py                         60      4    93%   84-85, 123-124
src/bff/middleware/security_headers.py       21      0   100%
src/bff/core/errors.py                       34      0   100%
src/bff/main.py                              32      0   100%
```

The four uncovered lines in `csrf.py` are the defensive `except ValueError`
branches in `urllib.parse.urlsplit` parsing — Python's `urlsplit` is
forgiving and rarely raises, but the guards are kept so a malformed
`Referer` (or future Python tightening) cannot crash the middleware.

### Completion Notes List

- **All 12 ACs satisfied.** All 10 tasks and their subtasks marked complete.
- **`CsrfMiddleware`** authored at `src/bff/auth/csrf.py`. Exempts safe
  methods (GET/HEAD/OPTIONS) unconditionally; on state-changing methods,
  reads `bff_csrf` cookie + `X-CSRF-Token` header, compares with
  `hmac.compare_digest`, then validates the request's `Origin`
  (`Referer` fallback when `Origin` absent or `"null"`) against
  `BFF_BASE_URL` as a `(scheme, hostname, port)` triple. Rejections emit
  the documented 403 `csrf_invalid` envelope and log a WARN classifier
  (`csrf_header_missing`, `csrf_token_mismatch`, `csrf_origin_mismatch`).
  Never logs the cookie/header value; truncates `Referer` to hostname.
- **`SecurityHeadersMiddleware`** authored at
  `src/bff/middleware/security_headers.py`. Pure additive: attaches the
  exact CSP directive list mandated by architecture A8 to responses where
  the request's `Accept` header contains `text/html` AND the path is not
  in the JSON API exclusion set (`/auth/`, `/api/`, `/v1/`, `/health`).
  The CSP string is module-level and asserted byte-for-byte by the test
  matrix. Resolves the location discrepancy in architecture C-C Mapping
  line 1193 (which named `app.py`) by placing the middleware in a new
  `middleware/` subpackage, leaving `main.py` as the wiring file —
  matches Story 1.3's entry-point precedent.
- **`ErrorCode.CSRF_INVALID`** added at `src/bff/core/errors.py` with
  wire value `csrf_invalid` (lower_snake per architecture §C5) → HTTP 403
  (per architecture §Format Patterns line 684).
- **Middleware wired into `main.py`** with documented LIFO ordering.
  `SecurityHeadersMiddleware` is registered before `CsrfMiddleware`, so
  CSRF is the outer guard and SecurityHeaders is inner — a CSRF 403
  short-circuit bypasses CSP attachment (correct: the 403 is JSON, not
  HTML). The two new `app.add_middleware(...)` lines carry the
  `# ty: ignore[invalid-argument-type]` comment matching the
  CORSMiddleware precedent (D29).
- **Test surface added:** `tests/auth/test_csrf.py` (24 tests covering
  AC11 matrix rows 1–23 and 31, including safe-method passthrough,
  happy-path, missing/empty/mismatched cookie+header, cross-origin /
  cross-port / cross-scheme, `Origin: null` sandboxed-iframe handling,
  Referer fallback, length-mismatch defense-in-depth, and the
  middleware-ordering proof that CSRF rejections carry no CSP) and
  `tests/middleware/test_security_headers.py` (8 tests covering AC11
  rows 24–30 plus belt-and-braces `/health` + `/auth/login` HTML probes).
- **`client_with_csrf` fixture** added to `tests/conftest.py`. Pre-seeds
  the `bff_csrf` cookie + `X-CSRF-Token` header + same-origin `Origin`,
  and patches `settings.bff_base_url` to `http://test` (function-scoped
  monkeypatch unwinds between tests). Sibling of `client` and
  `client_no_redirects`.
- **`test_validation_error_via_http`** (`tests/core/test_errors.py`)
  migrated to `client_with_csrf` — without the migration, CSRF would
  intercept the POST at 403 before reaching the 422 validator path that
  test was asserting.
- **CORS tests untouched** — they use GET / OPTIONS only, both of which
  are safe methods and pass through unconditionally.
- **All gates green:** 264 passed (up from 223 in Story 1.5); total
  coverage 97.35%; ruff/ty/format/compose/build all clean.
- **No new deferred items.** D44 (module-level `_session_service`
  singleton) remains intentionally deferred per the story spec.
- **Cross-story dependency unblocked:** Story 1.7's `POST /auth/logout`
  scenario 15 (`@pytest.mark.skipif(not _csrf_middleware_installed())`)
  will auto-unskip once 1.7's implementation references the now-shipped
  `bff.auth.csrf.CsrfMiddleware` import sentinel.

### File List

**New files:**

- `services/bff/src/bff/auth/csrf.py` — `CsrfMiddleware` (double-submit + Origin/Referer).
- `services/bff/src/bff/middleware/__init__.py` — empty package marker.
- `services/bff/src/bff/middleware/security_headers.py` — `SecurityHeadersMiddleware` (CSP).
- `services/bff/tests/auth/test_csrf.py` — 24 tests for the CSRF middleware (AC11 rows 1–23, 31).
- `services/bff/tests/middleware/__init__.py` — empty.
- `services/bff/tests/middleware/test_security_headers.py` — 8 tests for the CSP middleware (AC11 rows 24–30 + `/health` HTML probe).

**Modified files:**

- `services/bff/src/bff/core/errors.py` — added `CSRF_INVALID = ("csrf_invalid", "CSRF token missing or invalid", 403)` after `AUTH_STATE_INVALID`.
- `services/bff/src/bff/main.py` — added `CsrfMiddleware` + `SecurityHeadersMiddleware` imports and the two `app.add_middleware(...)` calls between the CORS install and exception-handler registration; both new lines carry the `# ty: ignore[invalid-argument-type]` comment matching the CORS precedent.
- `services/bff/tests/conftest.py` — added `client_with_csrf` fixture and `_CSRF_FIXTURE_VALUE` constant (43-char placeholder matching `secrets.token_urlsafe(32)` length); imported `bff.core.config.settings` for the in-fixture monkeypatch.
- `services/bff/tests/core/test_errors.py` — added `test_csrf_invalid_enum_shape`; migrated `test_validation_error_via_http` to `client_with_csrf` so the validator path is reachable with CSRF active.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-6-bff-csrf-middleware-csp-header` flipped `ready-for-dev` → `in-progress` → `review`; `last_updated` rolled to 2026-05-15.

**Untouched (verified):**

- All Story 1.1–1.5, 1.8, 1.9 deliverables outside the files listed above.
- `services/bff/pyproject.toml` / `uv.lock` — no dep changes (everything middleware needs is stdlib + already-imported Starlette).
- `services/bff/src/bff/api/{auth.py, me.py, health.py, v1/}` — unchanged; existing endpoints flow through the new middleware without modification.
- `services/bff/src/bff/auth/{__init__.py, keycloak_cookie_session.py, pkce.py}` — unchanged.
- `services/bff/src/bff/services/session_service.py` — unchanged.
- `services/bff/src/bff/models/entities/` — unchanged (no schema changes).
- `services/bff/alembic/` — no new migration.
- `services/bff/tests/api/test_cors.py` — verified passes unchanged (GET/OPTIONS only).
- `compose/`, `keycloak/`, `docker-compose.yml`, `keycloak/realm-bmad-books.json`, `services/bff/Dockerfile` — unchanged.
- `spa/`, `e2e/` — not in scope.

## Change Log

- **2026-05-15** — Story 1.6 implementation complete. Authored `CsrfMiddleware`
  (double-submit cookie + `X-CSRF-Token` header + same-origin Origin/Referer
  check per architecture A5) and `SecurityHeadersMiddleware` (CSP per
  architecture A8); wired both into `main.py` with documented LIFO ordering.
  Added `ErrorCode.CSRF_INVALID` and a `client_with_csrf` test fixture.
  33 new tests (24 CSRF + 8 CSP + 1 enum); all 264 BFF tests green; total
  coverage 97.35% (per-module: csrf.py 93%, security_headers.py 100%);
  ruff/ty/format/compose/build all clean. Status → review.
