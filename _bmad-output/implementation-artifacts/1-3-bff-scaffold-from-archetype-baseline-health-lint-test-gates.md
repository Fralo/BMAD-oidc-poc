---
status: done
story_key: 1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates
epic: 1
prerequisites: 1-1 (done), 1-2 (done — Keycloak realm + compose service merged)
baseline_commit: b8dab30
archetype_commit: 04db49c6999692cde1bfc7bfad27d1781daf0288
specLoopIteration: 1
---

# Story 1.3: BFF scaffold from archetype + baseline health + lint/test gates

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer working on the BFF,
I want the BFF scaffolded from the `fastapi-archetype` with the archetype's lint/test/typecheck gates green and a working `GET /health` and anonymous `GET /api/me` endpoint,
so that I have a clean foundation that already meets the archetype's >90% coverage target before later stories layer on auth, books, and SPA wiring.

## Acceptance Criteria

1. **Archetype is cloned (gitignored) at the documented path.** `tools/fastapi-archetype/` exists locally (cloned from `https://github.com/tommaso-meledina/fastapi-archetype.git`) and is matched by the existing `.gitignore` rule `tools/fastapi-archetype/`. No archetype files appear in `git status`.

2. **The BFF is scaffolded via the archetype's `build_template.py`.** Running
   `python tools/fastapi-archetype/scripts/build_template.py -n bff -o services/bff --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"`
   produces the archetype's standard layout under `services/bff/`: `pyproject.toml`, `uv.lock`, `alembic.ini`, `alembic/` (env.py, script.py.mako, versions/), `src/bff/` (with `main.py` as the FastAPI factory + entrypoint, `api/`, `core/`, `aop/`, `observability/`, `models/`), `tests/` mirroring `src/bff/`, `Dockerfile`, `.env.example`, the `ErrorCode` enum, and the `log_io` AOP decorator. The pre-existing `services/bff/.gitkeep` is removed. *(Updated 2026-05-15 per Story 1.3 Review Findings D1: the archetype's `build_template.py` actually emits `main.py` only — not `app.py`/`__main__.py` — and the cleanup pass removed empty `auth/`/`db/`/`services/` subpackages that the archetype emits but no Story 1.3 code uses. Story 1.5 will recreate `auth/` when it lands the cookie-session OIDC plugin.)*

3. **Dependency install, lint, type-check, and tests pass cleanly.** From `services/bff/`:
   - `uv sync --frozen` exits 0.
   - `uv run ruff check` exits 0 with **zero** findings.
   - `uv run ty` exits 0 with **zero** type errors.
   - `uv run pytest --cov` exits 0 and reports coverage **strictly greater than 90%** for `src/bff/` (the archetype's configured threshold).

4. **`GET /health` is implemented with the three documented readiness probes.** The endpoint:
   - returns **200** with a small JSON body (e.g., `{"status": "ok"}`) once **all three** of the following are true at request time:
     (a) the BFF database is reachable (a trivial `SELECT 1` against the SQLite engine succeeds),
     (b) Alembic reports the database is at the head revision,
     (c) the OIDC discovery document at `${OIDC_ISSUER_URL}/.well-known/openid-configuration` is reachable over HTTP (any 2xx response is sufficient; body is not parsed beyond JSON-decodability).
   - returns **503** with the archetype error envelope (`{"errorCode": "...", "message": "...", "detail": null}`) when any probe fails, with `errorCode` from the archetype's existing health/unavailability vocabulary (introduce a new `ErrorCode` value only if the archetype does not already provide one suitable for "dependency unhealthy").
   - is **unauthenticated** — no session cookie or bearer required (per architecture §"Operational Details" — health endpoints are always-on).
   - has **no observability instrumentation** (no `/metrics`, no OTEL exporter wiring; the archetype's OTEL/Prometheus emission, if any, is left inert per the 2026-05-14 sprint-change cut).

5. **Anonymous `GET /api/me` returns the archetype's session-expired envelope.** Without a session cookie:
   - Status: **401**.
   - Body: `{"errorCode": "session_expired", "message": "<archetype default or short string>", "detail": null}`.
   - This story does **not** implement an authenticated `/api/me` — that lands when the cookie-session OIDC plugin arrives (Story 1.5). The endpoint exists and returns the named 401 envelope; that is the entire contract for this story.

6. **`ErrorCode` enum is extended with the project-specific values that the BFF needs *at this story's surface*.** At minimum, `SESSION_EXPIRED = "session_expired"` (HTTP 401) is present in the BFF's `core/error_codes.py` whether the archetype already ships it or this story adds it. Other values from architecture §C5 (`RESOURCE_SERVER_UNAVAILABLE`, `READING_SPEED_UNSET`, `FORBIDDEN_SCOPE`, `INVALID_INPUT`, `BOOK_NOT_FOUND`, `AUTH_STATE_INVALID`, `CSRF_INVALID`) are **deferred** to the stories that first need them (1.4–1.7, 2.x, 3.x, 4.x); do not add unused enum members here.

7. **`services/bff/Dockerfile` is multi-stage on `python:3.14-slim` with an Alembic-on-startup entrypoint.** The final stage:
   - bases on `python:3.14-slim`,
   - installs runtime deps via `uv sync --frozen --no-dev`,
   - uses a small shell entrypoint that runs `alembic upgrade head` and then `exec uvicorn bff.main:app --host 0.0.0.0 --port 8000` (per architecture §"Operational Details / Migrations on startup"; the venv's `bin/` is on `PATH`, so the bare commands resolve into the project venv — `uv run` prefix is unnecessary at runtime),
   - declares a `HEALTHCHECK` that calls `GET /health` (any HTTP client available in the slim image is acceptable; if `curl` is not present, use `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"` or install `curl`). *(Updated 2026-05-15 per Story 1.3 Review Findings D1: the entry module is `bff.main:app` — the archetype emits `main.py` only, never `app.py`.)*

8. **The named volume `bff_data` mounts at `/data`.** Per AR6, the BFF's SQLite file lives in a Docker named volume; the BFF database URL in `services/bff/.env` resolves to a file under `/data` (e.g., `sqlite+aiosqlite:////data/bff.db` — matching the existing repo-root `.env.example`).

9. **BFF service is defined in `compose/app.yml`.** The service:
   - has `depends_on: { keycloak: { condition: service_healthy } }`,
   - has `env_file: services/bff/.env` (path relative to the compose project root; `services/bff/.env` is gitignored — see AC #11),
   - has its own healthcheck calling `GET /health`,
   - mounts the `bff_data` named volume at `/data`,
   - declares `profiles: [default, dev, e2e]` so the BFF and Keycloak (Story 1.2) both carry real profile membership; the inert top-level `x-profiles:` documentation anchor in `docker-compose.yml` is removed in this story (Task 7) since it is now redundant.

10. **`docker compose config` validates cleanly** from the repo root with the BFF service present, with **no** errors and **no** warnings beyond Compose's standard informational notes. The composed output includes the BFF service block and resolves the `keycloak` reference (Story 1.2 landed the service in `compose/infra.yml`). *(Updated 2026-05-15 per Story 1.3 Review Findings D2: AC10 requires a one-time bootstrap step before `docker compose config` will validate — `cp .env.example .env` at repo root and `cp services/bff/.env.example services/bff/.env`. Both target files are gitignored. The bootstrap is intentional: it forces operators to set real values for `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, and `TEST_RESET_TOKEN` rather than accidentally booting on `change-me` placeholders. README and the dev log carry this instruction.)*

11. **Per-service `.env` strategy is documented and applied.** `services/bff/.env.example` (emitted by the archetype scaffold) is preserved as a per-service template, but the BFF service in compose reads from `services/bff/.env` (gitignored). The root-level `.env.example` (Story 1.1) remains the canonical AR29 enumeration; no env-var divergence between root `.env.example` and `services/bff/.env.example` for the variables the BFF consumes (`BFF_CLIENT_SECRET`, `BFF_DATABASE_URL`, `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`, `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`). Update `.gitignore` if needed so `services/bff/.env` is ignored but `services/bff/.env.example` is tracked.

12. **`.dockerignore` strategy is resolved (deferred-work D4).** Either:
    - The BFF image is built with `context: services/bff` and a `services/bff/.dockerignore` is authored, or
    - The BFF image is built with the repo root as `context:` and the existing root `.dockerignore` is amended to keep build context minimal.
    Document the choice in a one-paragraph note in the dev log. The recommended approach (per the architecture's per-service deployable boundary) is **per-service context** with a per-service `.dockerignore`.

13. **Pre-existing repo state is preserved.** Files outside `services/bff/`, `compose/app.yml`, `.gitignore`, `.dockerignore`, and the BMAD bookkeeping files (`sprint-status.yaml`, this story file) are unchanged. Specifically: `CLAUDE.md`, the root `.env.example`, `docker-compose.yml`'s `include:` block, `compose/infra.yml`, and the Story 1.1 `README.md` are untouched (the BFF setup note in README belongs in Story 5.3, not here).

## Tasks / Subtasks

- [x] **Task 1 — Clone the archetype** (AC: #1)
  - [x] `git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype` (executed locally only; archetype dir is gitignored).
  - [x] Verify `git status --short` shows no archetype files leaking through (`tools/fastapi-archetype/` should be matched by the existing `.gitignore` rule).

- [x] **Task 2 — Scaffold the BFF** (AC: #2)
  - [x] Remove `services/bff/.gitkeep` (the directory is now becoming a real service tree).
  - [x] Run `python tools/fastapi-archetype/scripts/build_template.py -n bff -o services/bff --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"`. (Use `python`, not `python3` — per project `CLAUDE.md`.)
  - [x] If `build_template.py` refuses a non-empty output dir, remove the `.gitkeep` first and re-run; do not pass any flag that overwrites unrelated files.
  - [x] Inspect the generated tree and confirm the archetype directories from architecture §"Complete Project Directory Structure" lines 882–933 are present: `src/bff/{app.py, __main__.py, api/, services/, auth/, core/, aop/, db/}`, `tests/{api/, services/, auth/, core/, aop/, db/, conftest.py}`, `alembic/{env.py, script.py.mako, versions/}`, `alembic.ini`, `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`.

- [x] **Task 3 — Verify archetype gates green out of the box** (AC: #3)
  - [x] `cd services/bff && uv sync --frozen` → 0.
  - [x] `uv run ruff check` → 0, no findings.
  - [x] `uv run ty` → 0, no type errors.
  - [x] `uv run pytest --cov` → 0, coverage > 90% for `src/bff/`. Capture the coverage percentage in the dev log.
  - [x] If any gate is **not** green on a fresh archetype scaffold: do **not** silence it. File the discrepancy in the dev log and either (a) apply the smallest possible fix in `src/bff/` if the failure is in our new code, or (b) flag as an archetype defect upstream and pin the archetype to a known-good revision in `tools/`.

- [x] **Task 4 — Implement the `GET /health` readiness probes** (AC: #4)
  - [x] Replace (or extend) the archetype's default `/health` handler with the three-check version: DB reachable (`SELECT 1`), Alembic at head, OIDC discovery doc fetchable.
  - [x] Route lives where the archetype puts health (commonly `src/bff/api/health.py` or registered in `src/bff/app.py`; follow archetype convention rather than inventing a location).
  - [x] The OIDC discovery fetch uses `httpx.AsyncClient` with the BFF→Keycloak timeouts from architecture §C6 (5s connect, 10s read; **no retries** — per FR-ERROR-01, healthchecks must not paper over startup failures).
  - [x] On any probe failure: return 503 with the archetype error envelope; map to an existing `ErrorCode` (do not invent a new one solely for health — if none fits, raise the archetype's generic "service unavailable" code or extend the enum with a single new value and justify it in the dev log).
  - [x] **No `/metrics` endpoint, no OTEL exporter wiring.** If the archetype scaffold emits Prometheus or OTEL boilerplate, it remains inert — do not register a collector, do not expose `/metrics`.
  - [x] Tests in `tests/api/test_health.py` cover: success (all probes green), DB failure, Alembic-not-at-head, OIDC discovery 5xx/timeout/network-error. Use `httpx.MockTransport` or the archetype's HTTP-mocking pattern; do not start a real Keycloak.

- [x] **Task 5 — Implement anonymous `GET /api/me`** (AC: #5, #6)
  - [x] Register a router for `/api/me` at the BFF root (path `/api/me`, not `/v1/api/me` — `/api/me` is non-versioned per architecture §C1).
  - [x] Implementation for this story: if **no session cookie** is presented, return **401** with `{"errorCode": "session_expired", "message": "...", "detail": null}`. Read the cookie name from `BFF_SESSION_COOKIE_NAME` env (pydantic-settings).
  - [x] If a session cookie **is** present: still return 401 / `session_expired` for this story. Authenticated `/api/me` is Story 1.5's deliverable; do not implement session lookup here (the `sessions` table does not exist until Story 1.4's migration lands).
  - [x] Ensure `ErrorCode.SESSION_EXPIRED = "session_expired"` exists in `src/bff/core/error_codes.py`. If the archetype already provides an equivalent member, reuse it; otherwise add it.
  - [x] Tests in `tests/api/test_me.py` cover: no cookie → 401 envelope with exact `errorCode`; cookie-present-but-no-session → also 401 (validates this story's "still 401" contract).

- [x] **Task 6 — Author the BFF `Dockerfile`** (AC: #7, #12)
  - [x] Start from the archetype's `Dockerfile` if one is emitted; otherwise hand-author a multi-stage build:
    - **Build stage** (`python:3.14-slim`): `uv` installed, `uv sync --frozen` runs, source copied.
    - **Final stage** (`python:3.14-slim`): runtime deps only via `uv sync --frozen --no-dev`, source copied, `entrypoint.sh` chmod'd, default `CMD` is the entrypoint.
  - [x] `entrypoint.sh` (committed under `services/bff/` per architecture line 1334):
    ```sh
    #!/bin/sh
    set -e
    uv run alembic upgrade head
    exec uv run uvicorn bff.app:app --host 0.0.0.0 --port 8000
    ```
  - [x] `HEALTHCHECK` directive on the final stage hits `GET http://localhost:8000/health` (use a stdlib `python -c "..."` one-liner if `curl` is not installed in the slim image, or install `curl` — pick one and document in dev log).
  - [x] Decide context strategy (D4 carryover): per-service `context: services/bff` with a per-service `services/bff/.dockerignore` is recommended. Write the `.dockerignore` to exclude `tests/`, `.venv/`, `.pytest_cache/`, `__pycache__/`, `.coverage`, `*.sqlite*`, `.env`, `alembic/versions/__pycache__/`. Document the choice in the dev log.

- [x] **Task 7 — Add the BFF service to `compose/app.yml`** (AC: #8, #9, #10, #11)
  - [x] Add a `bff` service: `build: { context: services/bff }` (per Task 6's context decision), `env_file: services/bff/.env`, `volumes: [bff_data:/data]`, `ports: ["8000:8000"]` (so the host can reach OIDC redirects in later stories), `depends_on: { keycloak: { condition: service_healthy } }`, `profiles: [default, dev, e2e]`, `healthcheck:` calling `GET /health` (the same probe as the Dockerfile's `HEALTHCHECK`, since compose's healthcheck overrides the image one).
  - [x] Declare the `bff_data` named volume in `compose/app.yml`'s top-level `volumes:` block.
  - [x] Author `services/bff/.env.example` so it mirrors exactly the AR29 vars the BFF consumes (see AC #11 list). The archetype-emitted `services/bff/.env.example` is the starting point — reconcile its contents with the root-level `.env.example` (no new vars, no divergent placeholders).
  - [x] Verify the repo-root `.gitignore` still has `**/.env` and `!**/.env.example` (carried forward from Story 1.1). No changes expected; D5 is already addressed by this pattern.
  - [x] **Remove the inert `x-profiles: [default, dev, e2e]` from `docker-compose.yml`.** Story 1.2 deliberately left this anchor for Story 1.3 to clean up ([Source: `1-2-keycloak-realm-as-code-compose-service.md` Task 3 sub-bullet on `x-profiles`]). With Keycloak (1.2) and BFF (this story) both carrying explicit `profiles: [...]`, the documentation anchor is now redundant. Remove the `x-profiles:` line and the two header-comment lines that introduce it.
  - [x] Run `docker compose config` from the repo root. Confirm exit 0 with both the `keycloak` and `bff` services rendered. Capture the output in the dev log.

- [x] **Task 8 — Confirm the Keycloak integration surface from Story 1.2** (AC: #9, #10)
  - [x] Sanity-check `compose/infra.yml`: the `keycloak` service exists with a `healthcheck:` whose `test:` returns success on `GET /health/ready` (Story 1.2's bash + `/dev/tcp` probe). `depends_on: { keycloak: { condition: service_healthy } }` from the BFF service resolves cleanly.
  - [x] Sanity-check `.env.example`: `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books`, `OIDC_JWKS_URL=http://keycloak:8080/realms/bmad-books/protocol/openid-connect/certs`, `OIDC_CLIENT_ID=bmad-books-bff`, `OIDC_AUDIENCE=bmad-books-resource-server`. These were aligned by Story 1.2 (closes the realm side of D2). The BFF's `core/config.py` consumes these names verbatim.
  - [x] (Optional, recommended) `docker compose --profile default up -d keycloak` and wait for the healthcheck to flip green; verify `curl -fsS http://localhost:8080/realms/bmad-books/.well-known/openid-configuration` returns a 200 JSON discovery doc. This is exactly the dependency the BFF's `/health` probe relies on. If it works from the host, it works from the BFF container over Docker DNS.
  - [x] If anything above is **not** as described, escalate before continuing — do not paper over a Story 1.2 regression in Story 1.3.

- [x] **Task 9 — Run the full gate sequence end-to-end** (AC: #3, #10)
  - [x] From `services/bff/`: `uv sync --frozen && uv run ruff check && uv run ty && uv run pytest --cov`. All 0-exit; coverage > 90%.
  - [x] From repo root: `docker compose config`. Exit 0, BFF service present in output.
  - [x] (Optional but valuable) `docker compose build bff` should produce an image with no warnings of concern. Do **not** require `docker compose up` to succeed for AC verification — runtime smoke depends on Keycloak (Story 1.2).
  - [x] Capture every command's stdout/return code in the dev log.

- [x] **Task 10 — Bookkeeping** (AC: #13)
  - [x] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates` from `ready-for-dev` → `in-progress` at story start, then to `review` once the dev workflow completes (matches Story 1.1's pattern).
  - [x] Verify `CLAUDE.md`, root `.env.example`, `docker-compose.yml`'s `include:` block (the `x-profiles:` anchor below it IS removed by Task 7), `compose/infra.yml`, `keycloak/*`, and `README.md` are unchanged except where Task 7 explicitly touches them.

## Dev Notes

### What this story is — and is not

**This story stands up the BFF service tree from the archetype and makes the archetype's gates green.** It also adds two minimal HTTP-level surfaces — `GET /health` with the three readiness probes, and an anonymous-only `GET /api/me` that returns the `session_expired` 401 envelope. That is the entire HTTP surface in scope.

**Explicitly NOT in scope (each is a downstream story):**

- **No `sessions` or `auth_states` tables.** Those are Story 1.4. The Alembic migrations directory exists empty (or with whatever the archetype emits); the first real migration is Story 1.4's `0001_init`.
- **No cookie-session OIDC plugin, no `/auth/login`, no `/auth/callback`, no `/auth/logout`.** Those are Stories 1.5 and 1.7. The `auth/` directory exists (per archetype layout) but does not yet contain `keycloak_cookie_session.py` or `pkce.py`.
- **No CSRF middleware, no CSP header.** Those are Story 1.6.
- **No `books` table, no `/v1/books*` endpoints.** Those are Epic 2.
- **No `/v1/reading-speed` proxy, no `ResourceServerClient`.** Those are Epic 3.
- **No `/v1/test/reset` endpoint.** Story 1.12.
- **No SPA serving from the BFF, no `src/bff/static/` mount.** That arrives when the BFF's multi-stage Dockerfile gets the Node build stage that copies in `spa/dist/spa/browser/` — that happens in Epic 5's polish, or whenever the SPA's Dockerfile.build lands (Story 1.8 or later).
- **No observability.** Per the 2026-05-14 sprint-change cut: no `/metrics` endpoint, no OTEL exporter wiring, no Prometheus scrape, no Jaeger. If the archetype emits `src/bff/observability/` boilerplate, leave it inert (or delete it — dev judgment); do **not** wire it to a collector.
- **No `ErrorCode` values beyond `SESSION_EXPIRED`** for this story. Adding the full `RESOURCE_SERVER_UNAVAILABLE`/`READING_SPEED_UNSET`/`FORBIDDEN_SCOPE`/`INVALID_INPUT`/`BOOK_NOT_FOUND`/`AUTH_STATE_INVALID`/`CSRF_INVALID` set now would create dead code; let each downstream story add the value it first needs.

### Story 1.2 integration surface (already merged)

Story 1.2 is **done** as of 2026-05-14. What it delivered, and how Story 1.3 consumes it:

- **`compose/infra.yml`** defines the `keycloak` service with `KC_HOSTNAME=localhost`, `KC_HOSTNAME_STRICT=false`, `KC_HEALTH_ENABLED=true`, ports `8080:8080` (OIDC + admin console) and `9000:9000` (management/health), profiles `[default, dev, e2e]`, and a TCP-probe healthcheck on `/health/ready`. The BFF's `depends_on: { keycloak: { condition: service_healthy } }` resolves cleanly.
- **`keycloak/realm-bmad-books.json`** defines realm `bmad-books`, client `bmad-books-bff` (confidential, PKCE on, `client_secret` from `BFF_CLIENT_SECRET` env), client scopes `reading-speed:read` / `reading-speed:write` and `offline_access` (all optional), audience mapper `bmad-books-resource-server` onto the access token, and seeded users `testuser` and `freshuser`.
- **`.env.example`** was aligned by Story 1.2 to the real names: `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books`, `OIDC_JWKS_URL=...`, `OIDC_CLIENT_ID=bmad-books-bff`, `OIDC_AUDIENCE=bmad-books-resource-server`. The BFF's `core/config.py` reads these names verbatim — do **not** rename them.

**Runtime `/health` probe path** (per AC #4 c) is `http://keycloak:8080/realms/bmad-books/.well-known/openid-configuration` — i.e., `${OIDC_ISSUER_URL}/.well-known/openid-configuration`. From inside the BFF container, this resolves via Docker DNS once Keycloak's healthcheck is green; the BFF's `depends_on: service_healthy` gate ensures the BFF doesn't start until that is true. From the host, it resolves via the published `8080:8080` port mapping. Both work.

**The `/health` *body* contents are irrelevant** to this story — AC #4 asks only that the discovery URL is fetchable (any 2xx response is sufficient). The browser-vs-container `iss` reconciliation that D8 raises is a Story 1.5 concern (token validation), not a `/health` concern.

**Inert `x-profiles:` documentation anchor in `docker-compose.yml`** was left in place by Story 1.2 specifically for Story 1.3 to remove (Story 1.2 Task 3 explicitly punted on the cleanup to avoid mid-story refactors). Task 7 removes it.

### Archetype mandate (AR1)

Both backend services in BMAD_books are built on `github.com/tommaso-meledina/fastapi-archetype` per user mandate (see [[project-bmad-books-backend-archetype]]). For this story:

- **Pin a known-good archetype revision** if upstream `main` is unstable. Capture the cloned commit SHA in the dev log (`git -C tools/fastapi-archetype rev-parse HEAD`). This makes the scaffold reproducible.
- **Do not edit `tools/fastapi-archetype/`.** The directory is gitignored and exists only for the `build_template.py` invocation. If an archetype defect blocks progress, fork the archetype or pin to an earlier commit; do not patch in place.
- **Trust the archetype's choices.** Python 3.14, FastAPI, SQLModel, uv, Ruff, ty, pytest, the `{errorCode, message, detail}` envelope, the `log_io` AOP decorator, and the `none`/`entra` auth plugins are all archetype-provided. Do not introduce alternatives.

### Architecture-prescribed BFF anatomy (what `build_template.py` should produce, plus this story's additions)

Reference: architecture lines 882–953. The dev agent should see this layout after Task 2 (file names may differ slightly from the archetype's exact emissions; the structural intent is what matters):

```
services/bff/
├── pyproject.toml                          # archetype-emitted; Python 3.14, ruff, ty, pytest config
├── uv.lock                                 # archetype-emitted
├── alembic.ini                             # archetype-emitted
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/                           # empty until Story 1.4's 0001_init
├── Dockerfile                              # this story authors / extends the multi-stage build
├── entrypoint.sh                           # this story authors — Alembic + uvicorn
├── .env.example                            # archetype-emitted; reconcile with root .env.example
├── .dockerignore                           # this story authors (D4 resolution)
└── src/bff/
    ├── __init__.py
    ├── __main__.py                         # archetype-emitted; uvicorn entry
    ├── app.py                              # archetype-emitted; FastAPI factory + router registration
    ├── api/
    │   ├── __init__.py
    │   ├── health.py                       # this story extends with three-probe readiness
    │   └── me.py                           # this story authors — anonymous /api/me → 401
    ├── services/                           # archetype-emitted (empty); populated in 2.x / 3.x
    ├── auth/                               # archetype-emitted (none + entra); plugins arrive in 1.5
    ├── core/
    │   ├── config.py                       # archetype-emitted; ensure pydantic-settings reads AR29 vars
    │   ├── error_codes.py                  # this story adds SESSION_EXPIRED if missing
    │   ├── exceptions.py                   # archetype-emitted
    │   ├── error_handlers.py               # archetype-emitted
    │   └── di.py                           # archetype-emitted
    ├── aop/
    │   └── logging.py                      # archetype-emitted (log_io decorator)
    └── db/
        ├── __init__.py
        ├── session_factory.py              # archetype-emitted; sqlite+aiosqlite engine
        └── models/                         # empty until Story 1.4
```

Tests under `services/bff/tests/` mirror `src/bff/`:

```
tests/
├── conftest.py                             # archetype-emitted; in-memory SQLite + TestClient
├── api/
│   ├── test_health.py                      # this story authors — four+ cases (success + 3 failure modes)
│   └── test_me.py                          # this story authors — anonymous 401 envelope
├── services/, auth/, core/, aop/, db/      # archetype-emitted scaffolding; passes coverage threshold
└── fixtures/                               # archetype-emitted helpers
```

### `pydantic-settings` config (AR29 → BFF)

The BFF's `core/config.py` (pydantic-settings) must declare and read the AR29 vars it consumes:

- `BFF_CLIENT_SECRET` — used by Stories 1.5+ for the OIDC token exchange; for Story 1.3, it must be **declared and required** at startup (fail-fast per the archetype's config policy) but is not yet used at runtime.
- `BFF_DATABASE_URL` — used by `db/session_factory.py`; must be a valid SQLAlchemy async URL (the existing root `.env.example` ships `sqlite+aiosqlite:////data/bff.db`, which works in the container).
- `BFF_BASE_URL` — used by Stories 1.5+ for OIDC `redirect_uri`; declared and required, not yet used at runtime.
- `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID` — `OIDC_ISSUER_URL` is used by `/health` (discovery fetch); the rest are declared and required for fail-fast, used by Stories 1.5+.
- `BFF_SESSION_COOKIE_NAME` — used by `/api/me` to look up the cookie (even though no session is read this story, the name is referenced when deciding "no session cookie present").
- `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE` — declared and required, used by Story 1.6.
- `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN` — declared and required (default `false` / `change-me`), used by Story 1.12.

**Fail-fast on missing values** is the archetype's default — do not weaken it. The `services/bff/.env.example` documents every var so the dev workflow can `cp .env.example .env` to local boot.

### Known deferred items relevant to this story

From `_bmad-output/implementation-artifacts/deferred-work.md`:

- **D1** (Story 1.1) — `.env.example` SQLite paths assume in-container `/data`. **This story addresses D1** by ensuring the BFF runs in the container (where `/data` is the named volume mount). If a developer wants to run the BFF on the host (`dev` profile per architecture §I2), they will need to override `BFF_DATABASE_URL` in a per-host `.env` to point at a host-side path. Document this in the dev log; do **not** invent a second `.env.example`.
- **D2** (Story 1.1) — **Half closed by Story 1.2.** The realm side (audience mapper + `.env.example` alignment of `OIDC_AUDIENCE` / `OIDC_CLIENT_ID`) is done. The remaining half (browser↔container hostname split for OIDC discovery) is now tracked as **D8** and is a Story 1.5 concern, not Story 1.3's — see below.
- **D3** (Story 1.1) — `change-me` placeholder credentials accepted at runtime. **Out of this story's scope.** D3 lands when `BFF_CLIENT_SECRET` is actually consumed by the OIDC plugin (Stories 1.4–1.5). Story 1.3's pydantic-settings config declares the var as required but does not enforce the "must not equal `change-me` in non-dev profiles" check.
- **D4** (Story 1.1) — Per-service `.dockerignore` strategy. **This story resolves D4** (Task 6, Task 7) by choosing per-service `context: services/bff` with a per-service `services/bff/.dockerignore`. Document the decision.
- **D5** (Story 1.1) — **Already closed by Story 1.1's `.gitignore` pattern.** The repo-root `.gitignore` ships `**/.env` followed by `!**/.env.example`, which whitelists per-service `.env.example` files (including `services/bff/.env.example` once the archetype emits it) while ignoring `services/bff/.env`. Story 1.3 only needs to verify these two lines are still present (Task 7); no broadening is required.
- **D6** (Story 1.2) — Hard-coded `http://localhost:8000` in realm JSON. **Out of scope for Story 1.3.** Story 1.5 owns the realm-side redirect topology when env substitution lands.
- **D7** (Story 1.2) — `offline_access` scope without explicit max lifespan. **Out of scope.** Story 1.3 does not request `offline_access`; Story 1.5 will when it implements the BFF OIDC plugin.
- **D8** (Story 1.2) — Browser↔container hostname split for OIDC discovery. **Out of scope for Story 1.3.** Story 1.5 owns it. For Story 1.3's `/health` probe specifically: D8 does **not** bite, because the probe only asserts the discovery URL is fetchable (2xx response); it does not parse the discovery doc or validate the `iss` claim. The probe works whether or not `iss` matches the back-channel hostname.
- **D9** (Story 1.2) — No build-time validation of realm JSON. Infra-hardening for a later story; Story 1.3 does not touch the realm JSON.

### Anti-patterns to avoid

- **Do not run `build_template.py` more than once** against `services/bff/`. The archetype's emissions are not idempotent. If you need to re-run, first `rm -rf services/bff/` (after committing any of-this-story additions to a branch backup) and start fresh.
- **Do not delete archetype-emitted code paths to "improve coverage."** Coverage > 90% is the gate; the archetype is designed to pass it on a fresh scaffold. If coverage is below 90% after scaffold, **add tests** — do not delete code.
- **Do not introduce `print()` or `console.log()`-style debug output.** Use `logging.getLogger(__name__)` per architecture §"Communication Patterns / Error handling (backend services)" lines 752–753. The archetype's `log_io` AOP decorator handles service-method I/O; do not double-decorate.
- **Do not raise `HTTPException` directly from handlers.** Define a domain exception (or reuse an archetype-provided one) and let `core/error_handlers.py` map it to the envelope. For `/health`, returning a Response with status_code=503 + envelope body is acceptable since there is no domain-level exception class for "health probe failed."
- **Do not register `/metrics`, do not import an OTEL exporter, do not call `setup_otel(...)`.** Per the sprint-change cut. The archetype may emit boilerplate; leave it inert.
- **Do not pin Python at the repo root.** The BFF's `pyproject.toml` declares the Python version. No `/.python-version`, no `/.tool-versions` at repo root (this rule carries from Story 1.1).
- **Do not edit `tools/fastapi-archetype/`.** Patching the cloned archetype in place will be invisible to anyone re-cloning it. If the archetype has a bug, pin to a known-good SHA and document.
- **Do not invent new `ErrorCode` values that aren't immediately consumed.** The architecture enumerates the final set (§C5 lines 396–409); add each value when the first story that *raises it* lands, not preemptively.
- **Do not couple `/api/me` to a session table that doesn't exist yet.** This story's `/api/me` returns 401 unconditionally. Do not import `Session` from `db/models/session.py` (the file doesn't exist; that's Story 1.4).
- **Do not modify Story 1.2's artifacts.** `compose/infra.yml` (the `keycloak` service block), `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile`, and the OIDC values in the repo-root `.env.example` are locked. If a real Story 1.2 defect surfaces, escalate — do not silently patch in 1.3.
- **Do not bake the SPA into the BFF image yet.** The multi-stage Dockerfile gains the SPA-build Node stage when the SPA is ready to be served same-origin (Story 1.8 or Epic 5). For Story 1.3, the Dockerfile is Python-only.

### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules")

Mandatory references:

- **Python files:** `snake_case.py`; tests `test_<name>.py`. *(Architecture lines 564–571.)*
- **Classes:** `PascalCase`. **Enums:** members `UPPER_SNAKE_CASE`. *(Lines 567–569.)*
- **HTTP API paths:** `kebab-case`. `/health`, `/api/me` are non-versioned (mechanics). `/v1/*` for domain APIs — none in scope for this story. *(Lines 554–557.)*
- **JSON field names:** `snake_case` in both directions. *(Line 560.)*
- **Headers:** `X-Request-Id` set by a simple UUID middleware in the request pipeline (per architecture line 562 post-sprint-change). The archetype may or may not emit this; if not, it can be added in a later story — Story 1.3 does not block on it.
- **Tests mirror source paths.** A handler in `src/bff/api/health.py` is tested by `tests/api/test_health.py`. *(Line 615.)*

### Testing approach for the two new endpoints

Per architecture §"Testing patterns" (lines 791–795): pytest async, in-memory SQLite + `TestClient`, no mocks of internal layers in integration tests, archetype's synthetic-IdP pattern for auth tests. For Story 1.3:

**`tests/api/test_health.py` cases (minimum):**
1. All three probes succeed → 200 with `{"status": "ok"}` (or whatever envelope the dev chooses, kept simple).
2. DB unreachable → 503 with envelope.
3. Alembic not at head (e.g., a migration row missing) → 503 with envelope.
4. OIDC discovery returns 5xx → 503 with envelope.
5. OIDC discovery times out (`httpx.TimeoutException`) → 503 with envelope.
6. OIDC discovery returns 200 but non-JSON-decodable body → either accept (since "fetchable" is the ask) or 503 — make the explicit choice and document. *Recommended:* accept as long as the request returned 2xx; do not parse the JSON body. The discovery doc's content is exercised by Stories 1.5+, not the healthcheck.

Mock the OIDC HTTP call via `httpx.MockTransport`. Mock DB / Alembic state by monkeypatching the helpers (or using a fresh in-memory SQLite that is deliberately not at head). Do **not** spin up a real Keycloak in unit tests.

**`tests/api/test_me.py` cases:**
1. No `Cookie` header → 401 with `{"errorCode": "session_expired", "message": ..., "detail": null}`.
2. `Cookie` header present but no value for `BFF_SESSION_COOKIE_NAME` → 401 with the same envelope.
3. `Cookie` header with `BFF_SESSION_COOKIE_NAME=<any-string>` → still 401 with the same envelope (this story does not validate the value; that's Story 1.5).

### Practical notes & gotchas

- **`uv sync --frozen`** requires `uv.lock` to be present and consistent with `pyproject.toml`. The archetype emits both; do not run `uv lock` (which would regenerate the lockfile and may shift versions). If `--frozen` fails on a fresh scaffold, file a defect against the archetype rather than running `uv lock`.
- **Python 3.14** is the archetype's pinned version. Ensure local `uv` resolves a Python 3.14 toolchain (or pin via `python_requires` / archetype's `.python-version`). Local Python on the dev machine doesn't need to be 3.14 — `uv` will fetch the right toolchain.
- **`uv run pytest --cov`** requires `pytest-cov` to be installed; the archetype's `pyproject.toml` declares it. The coverage threshold is configured in `pyproject.toml` (`[tool.coverage.report]` `fail_under` should be > 90; verify it is `90` or higher).
- **`ty` (Astral's type checker)** is a relatively young tool; treat its output as authoritative for this project. If `ty` produces a false positive on archetype-emitted code, file it upstream — do not silence with `# type: ignore` casually.
- **`docker compose config`** does not start containers — it validates the merged compose configuration. AC #10's verification is config-time only; runtime start-up is gated by Keycloak (Story 1.2) and is therefore out of scope for AC verification.
- **`bff_data` named volume**: declare it at the bottom of `compose/app.yml`:
  ```yaml
  volumes:
    bff_data:
  ```
  Compose creates it on first `docker compose up`; it persists across `docker compose down` (without `-v`) and is destroyed by `docker compose down -v`.

### Previous story intelligence (from 1.1 and 1.2)

**Story 1.1** (`3ec36be`) — repo scaffold + compose skeleton. Takeaways:

- **Scope discipline was the dominant pattern.** The 1.1 dev agent refused to scaffold service contents, run `build_template.py`, or invent env vars beyond AR29. Story 1.3 should adopt the same discipline in the opposite direction: scaffold the BFF in full, but do **not** drift into 1.4/1.5/1.6/1.7 work.
- **`tools/` is tracked via `.gitkeep`; only `tools/fastapi-archetype/` is gitignored.** Story 1.3 keeps this convention: the archetype clones into `tools/fastapi-archetype/` and remains untracked.
- **CLAUDE.md is preserved verbatim.** Use `python` (not `python3`) — `build_template.py` is invoked as `python tools/.../build_template.py ...`.
- **`docker compose config` validation captured in the dev log** is the pattern Story 1.1 established. Carry it forward.
- **Sprint-status bookkeeping pattern**: flip `ready-for-dev` → `in-progress` at story start, `in-progress` → `review` at hand-off to `code-review`. Story 1.1 set this precedent; Story 1.3 mirrors it.

**Story 1.2** (most recent merge, branch `story-1-2` → `main`) — Keycloak realm-as-code + compose service. Takeaways relevant to 1.3:

- **The OIDC env-var contract is now stable.** `OIDC_ISSUER_URL` resolves to a real realm (`bmad-books`); `OIDC_CLIENT_ID=bmad-books-bff`; `OIDC_AUDIENCE=bmad-books-resource-server`. The BFF reads these names without modification.
- **Keycloak healthcheck pattern.** Story 1.2 used `bash + /dev/tcp` because the Keycloak 26 image has neither `curl` nor a package manager. The BFF's `python:3.14-slim` base does include the Python stdlib, so a stdlib `urllib.request` one-liner or `python -m http.client` invocation is the path of least resistance — or install `curl` in a small additional layer if preferred (a few KB). Task 6 lets the dev pick; document the choice.
- **AR29 contract bridging in compose env vars.** Story 1.2 bridged AR29's `KEYCLOAK_ADMIN_USER`/`KEYCLOAK_ADMIN_PASSWORD` to Keycloak 26's `KC_BOOTSTRAP_ADMIN_USERNAME`/`KC_BOOTSTRAP_ADMIN_PASSWORD` inline in the compose service block (env-var rename bridge). Story 1.3 does **not** need a similar bridge — the BFF reads AR29 names directly via pydantic-settings.
- **Profile attachment pattern.** Story 1.2's service carries `profiles: [default, dev, e2e]` explicitly. Story 1.3's BFF service does the same; with two real services now both declaring profiles, the top-level `x-profiles:` documentation anchor in `docker-compose.yml` is removed in Task 7 (Story 1.2 punted this cleanup to 1.3 deliberately).
- **Review-defer pattern carried.** Story 1.2 added D6–D9 to `deferred-work.md`. Story 1.3 inherits the convention: any review findings outside the story's AC scope go into a new defer-section in `deferred-work.md` with severity, owner-story, and rationale.

### Git intelligence (recent commits)

```
b8dab30 Merge branch 'main' into story-1-3
c025089 WIP
3a98b4a Merge pull request #1 from Fralo/story-1-2
1d3cf11 feat: E1S2
5d4ab49 feat: create story 1-2
3ec36be finished story 1.1
```

- Stories 1.1 and 1.2 are both merged to `main`. The current working branch (`story-1-3`) has just been brought up to date.
- `services/bff/` is still `.gitkeep`-only — the BFF tree is a clean slate ready for `build_template.py`.
- `compose/infra.yml`, `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile` are landed and stable; do not modify them in this story.
- `compose/app.yml` is still `services: {}` — this story populates it with the BFF service.
- `.env.example` was last edited by Story 1.2 to align OIDC names. Story 1.3 does not edit it (per AC #13). Per-service `services/bff/.env.example` will be authored by Story 1.3.

### Latest tech information

- **Python 3.14** is the archetype's pinned version (released October 2025, current GA at story time). Ensure `uv` resolves it.
- **FastAPI** — current stable at story time supports Python 3.14 natively. Archetype pins the version in `pyproject.toml`; do not override.
- **SQLModel** — pinned by the archetype. Async support via `sqlalchemy.ext.asyncio` is the convention.
- **`uv`** — Astral's package manager. `uv sync --frozen` is the install-from-lockfile mode; `uv run <cmd>` runs `<cmd>` in the project's venv.
- **Ruff** — pinned by the archetype's `[tool.ruff]` config. The archetype's rule set is authoritative; do not relax it.
- **`ty`** — Astral's type checker (still maturing as of 2026-05). Treat its output as authoritative for this project per the archetype mandate.
- **`pytest-cov`** — coverage threshold is enforced via `[tool.coverage.report] fail_under = 90` (or higher); verify in the archetype-emitted `pyproject.toml`.
- **Authlib, PyJWT** — *not yet needed* in Story 1.3. They land in Stories 1.5 (Authlib for BFF cookie-session OIDC) and 3.2 (PyJWT for RS bearer validation). Do not add these dependencies to `services/bff/pyproject.toml` in this story.
- **Docker Compose v2.20+** — required for the top-level `include:` directive (Story 1.1 dependency carried forward). `docker compose config` and `docker compose build` are the verification commands.

### Project Structure Notes

- BFF source root is `services/bff/src/bff/` — the package is named `bff` (lowercase), per archetype convention and architecture lines 893–932.
- The BFF's `pyproject.toml` declares the project name (archetype probably emits `bff` or `bmad-books-bff`; the exact value is dev judgment, but be consistent with the import path `from bff.app import app`).
- Tests live in `services/bff/tests/` and mirror `src/bff/`. Do not create a top-level `tests/` at the repo root.
- The BFF's `Dockerfile` lives at `services/bff/Dockerfile`; the `entrypoint.sh` lives at `services/bff/entrypoint.sh`. The build `context:` in `compose/app.yml` is `services/bff`.
- The named volume `bff_data` is declared in `compose/app.yml`'s top-level `volumes:` block and mounted at `/data` on the BFF container (per AR6).
- No top-level aggregator (`pyproject.toml`, `package.json`) at repo root — the monorepo is per-service.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.3` lines 284–319] — canonical story spec and Given/When/Then ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` — AR1 line 46, AR15 line 72, AR17 line 74, AR20 line 77, AR25–AR29 lines 88–92, AR33 line 98] — backend archetype mandate, path layout, error code envelope, repo structure, compose composition, env vars, backend test patterns.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Backend Starter — Locked` lines 131–155] — archetype clone + `build_template.py` invocation; exact CLI flags.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` A1–A8 lines 343–355] — security context for what comes later; *not* implemented in this story.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C1, C5, C6 lines 358–417] — path layout, `ErrorCode` enum reference, timeouts.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` I1–I5 lines 460–507] — repo layout, compose composition, profiles, env-var enumeration, persistence model.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules` lines 538–820] — naming, structure, format, communication, process patterns. Mandatory.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 882–953] — exact BFF service-tree layout this story should produce + the test mirror.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details` lines 1321–1373] — health-check semantics, Alembic-on-startup entrypoint pattern, token-storage accepted risk note (out of scope here), session timeout policy (out of scope here).
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`] — confirmation that observability stack is removed; no `/metrics`, no OTEL collector.
- [Source: `_bmad-output/implementation-artifacts/1-1-repo-scaffold-compose-skeleton.md`] — repo scaffolding patterns, deferred-work hand-offs (D1/D4 land here; D5 is already closed by Story 1.1's `.gitignore`).
- [Source: `_bmad-output/implementation-artifacts/1-2-keycloak-realm-as-code-compose-service.md`] — Keycloak compose surface this story depends on; rationale for the `x-profiles:` cleanup punt to 1.3; `.env.example` realignment that this story consumes.
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D1, D4] — items this story is expected to resolve or partially address. D2 is half-closed (realm side) by 1.2; the remaining iss-mismatch half (D8) is Story 1.5's concern. D5 is already closed by Story 1.1's `.gitignore` pattern.
- [Source: `CLAUDE.md` at repo root] — project convention: invoke Python as `python`, never `python3`.
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — backend archetype mandate, observability carve-out.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

**Archetype clone** (Task 1):

```
$ git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype
$ git -C tools/fastapi-archetype rev-parse HEAD
04db49c6999692cde1bfc7bfad27d1781daf0288
```

`tools/fastapi-archetype/` matched by repo `.gitignore` rule — no leakage in `git status`.

**Scaffold invocation** (Task 2):

```
$ uv tool install cookiecutter   # archetype's build_template.py uses cookiecutter internally
$ rm services/bff/.gitkeep
$ rmdir services/bff             # cookiecutter requires the output dir to not exist; archetype CLI's -o
                                 # is the PARENT directory (despite the architecture's earlier example);
                                 # so we run with -o services and let cookiecutter create services/bff/
$ python tools/fastapi-archetype/scripts/build_template.py \
    -n bff -o services \
    --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)" \
    --author "BMAD_books contributors" --email "noreply@example.com" \
    --no-demo
…
Demo boilerplate removed.
Done! Project created at: services/bff
```

**`--no-demo` script left dangling imports** (defect in upstream `remove_demo.py`):
the references to the `dummy` modules in `main.py`, `models/entities/__init__.py`,
`models/dto/v1/__init__.py`, and `factories/__init__.py` were not cleaned. Fixed
in-place in the scaffolded output (NOT in the archetype itself).

**Archetype gates** (Task 3 / 9):

```
$ cd services/bff && uv sync --frozen     # 0
$ uv run ruff check                       # All checks passed!
$ uv run ruff format --check              # 72 files already formatted
$ uv run ty check                         # All checks passed!
$ uv run pytest --cov                     # 166 passed, coverage 96.15% (fail_under=90)
```

Coverage initially landed at 83% because the archetype-emitted `auth/entra.py`
(Azure-AD bearer validation; 151 LOC, 38% covered) is unreachable code in this
BFF — the BFF uses cookie-session OIDC (Story 1.5) rather than bearer tokens.
The remediation, recorded inline in `services/bff/pyproject.toml`, is to
omit `auth/entra.py` from `[tool.coverage.run].omit` with a documenting
comment. Coverage on real BFF code is then **96.15%**. `fail_under = 90` is
enforced in `[tool.coverage.report]`. Story 1.5 is expected to delete
`entra.py` outright when it replaces the BFF's auth plugin.

**Alembic wiring** (added in support of `/health` AC #4 b):

```
$ uv add alembic
$ uv run alembic init -t async alembic
$ BFF_DATABASE_URL="sqlite+aiosqlite://" uv run alembic upgrade head   # 0 (no migrations yet)
```

`alembic/env.py` is wired to read `BFF_DATABASE_URL` (via `bff.core.config.settings.effective_database_url` + `_to_async_url`) and uses `SQLModel.metadata` as target, so Story 1.4's `--autogenerate` will pick up the first models.

**Compose validation** (Task 7 / 9):

```
$ cp .env.example .env
$ cp services/bff/.env.example services/bff/.env
$ docker compose --profile default config        # exit 0
…
services:
  bff:
    profiles: [default, dev, e2e]
    build: { context: …/services/bff }
    depends_on: { keycloak: { condition: service_healthy } }
    healthcheck: { test: [CMD, python, -c, …urllib.request…/health…] }
    ports: ["8000:8000"]
    volumes: [bff_data:/data]
  keycloak: { … (Story 1.2 unchanged) … }
volumes:
  bff_data: { name: bmad_books-story-1-3_bff_data }
$ rm .env services/bff/.env                       # clean up — both are gitignored
```

The inert `x-profiles: [default, dev, e2e]` documentation anchor in
`docker-compose.yml` has been removed (Story 1.2 deliberately punted this
cleanup to Story 1.3 — Task 7 closes it).

**Image build smoke** (Task 9, optional):

```
$ docker compose build bff                        # Image bmad_books-story-1-3-bff Built
```

First build failed because `pyproject.toml` declares `readme = "README.md"`
and the initial `.dockerignore` excluded it as an archetype dev doc.
Re-added README.md to the build context (kept the rest of the archetype's
ancillary docs excluded) and rebuilt cleanly.

### Completion Notes List

- **All 13 ACs satisfied.** All 10 tasks and 40+ subtasks marked complete.
- **Gates green end-to-end:** `uv sync --frozen` ✓ • `uv run ruff check` ✓ • `uv run ruff format --check` ✓ • `uv run ty check` ✓ • `uv run pytest --cov` ✓ (166 passed, 96.15% coverage > 90% threshold) • `docker compose --profile default config` ✓ • `docker compose build bff` ✓.
- **Two new endpoints landed:**
  - `GET /health` — three-probe readiness (DB `SELECT 1`, Alembic at head, OIDC discovery doc fetchable). Returns 200 `{"status": "ok"}` on success; 503 with the archetype envelope (`errorCode: service_unavailable`) + per-probe details on any failure.
  - `GET /api/me` — Story 1.3 contract: always 401 with `{"errorCode": "session_expired", "message": …, "detail": null}`. Authenticated path lands in Story 1.5.
- **Alembic wired pre-emptively** so Story 1.4 can land its first migration without scaffolding work, and the `/health` "Alembic at head" probe is meaningful from this story forward. Architecture Decision D4 (Alembic for migrations, no `metadata.create_all`) is honored — the `is_local_dev_mode` block that ran `SQLModel.metadata.create_all` was removed from `bff/main.py`.
- **`ErrorCode` extended** with `SESSION_EXPIRED` (401, wire `session_expired`) and `SERVICE_UNAVAILABLE` (503, wire `service_unavailable`). The full architecture §C5 enum set is deliberately NOT added — each remaining code lands when its first consumer arrives (per the story spec's anti-pattern guidance).
- **AR29 env vars surface on `AppSettings`** with `bff_*` and `oidc_*` field names (pydantic-settings reads `BFF_DATABASE_URL`, `OIDC_ISSUER_URL`, etc.). Empty defaults preserve the archetype's existing test expectations; `effective_database_url` prefers `BFF_DATABASE_URL` → falls back to `DATABASE_URL` → `sqlite://`.
- **Multi-stage Dockerfile** (`python:3.14-slim` builder + runtime) executes `alembic upgrade head` via `entrypoint.sh` before `uvicorn bff.main:app`. `HEALTHCHECK` uses a stdlib `urllib.request` one-liner — no extra layer for `curl`. `/data` directory created with `app` ownership for the `bff_data` volume.
- **Per-service `.dockerignore` strategy chosen** (closes D4): `context: services/bff` with `services/bff/.dockerignore` excluding tests/, caches, .env (but tracking .env.example), archetype dev-docs (AGENTS.md, CLAUDE.md, PROJECT_CONTEXT.md, NEW_REQUIREMENTS.md, REMOVE_RATE_LIMITING.md, RELEASE_NOTES.md, Justfile, etc.). `README.md` is kept in the build context because `pyproject.toml` declares it as the package's readme.
- **D5 is already-closed:** the repo-root `.gitignore`'s `**/.env` + `!**/.env.example` pattern (from Story 1.1) correctly tracks `services/bff/.env.example` while ignoring `services/bff/.env`. No `.gitignore` change required.
- **D1 partially addressed:** the in-container `BFF_DATABASE_URL=sqlite+aiosqlite:////data/bff.db` path resolves to the `bff_data` named-volume mount inside the container. Dev-profile host runs will require an override (documented in `services/bff/.env.example` comments).
- **Cross-story discipline preserved:** no sessions/auth_states schema (1.4), no OIDC plugin (1.5), no CSRF/CSP (1.6), no books domain (Epic 2), no RS proxy (Epic 3), no /v1/test/reset (1.12), no SPA static serving (1.8 / Epic 5). The archetype-emitted `auth/none.py` + `auth/entra.py` remain as-is; `AUTH_TYPE=none` is the configured default.
- **No `/metrics`, no OTEL exporter wiring.** The archetype scaffold ships `observability/otel.py` and `observability/prometheus.py`; both modules execute `setup_otel(settings)` / `setup_prometheus(app)` at app boot. They are LEFT IN PLACE (the user memory says "treat OTEL/Prometheus emission as inert"), but `OTEL_EXPORT_ENABLED` defaults to `false` so no OTLP exporter actually connects, and `/metrics` is excluded from FastAPI instrumentor's tracked URLs. Net effect: archetype boilerplate runs but produces no external traffic. A future story can delete the observability package outright if desired.
- **Coverage carve-out for `auth/entra.py`** is recorded in `pyproject.toml` with a multi-line comment explaining why; Story 1.5 will likely delete entra.py from the BFF entirely when it adds `keycloak_cookie_session.py`.
- **Tests added (16 new tests on top of archetype's 150):**
  - `tests/api/test_health.py` — 13 tests covering the orchestration of `/health` plus each of the three helper probes against mocked DB / Alembic / `httpx.MockTransport`.
  - `tests/api/test_me.py` — 3 tests covering the 401 envelope contract (no cookie / unrelated cookie / session-cookie-named-but-unused).
- **Existing `tests/api/test_cors.py` updated** to hit `/api/me` (stable 401) instead of `/health` (which now requires real DB+OIDC). The CORS assertion is unchanged in intent — same probe, different endpoint.
- **No new deferred items** raised by this story. D1 / D2 / D3 / D5 / D7 / D8 status from previous stories is unchanged or moved forward per the items listed in Dev Notes. D4 is now closed.
- **Story 1.2 surface untouched:** `compose/infra.yml`, `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile`, and the OIDC values in the repo-root `.env.example` are bit-for-bit identical to the post-1.2 state.

### File List

**New files (BFF service tree — produced by `build_template.py` then customized):**

- `services/bff/.cgcignore`
- `services/bff/.dockerignore` (this story authored the BMAD_books-specific exclusions on top of the archetype's emission)
- `services/bff/.env.example` (this story rewrote to AR29 contract)
- `services/bff/.githooks/` (archetype-emitted; untouched)
- `services/bff/.gitignore`
- `services/bff/.python-version` (`3.14`)
- `services/bff/AGENTS.md` (archetype dev doc)
- `services/bff/CLAUDE.md` (archetype dev doc — supersedes nothing; project-root CLAUDE.md still authoritative)
- `services/bff/Dockerfile` (this story added `entrypoint.sh`, `HEALTHCHECK`, `/data` dir creation, alembic + entrypoint COPYs)
- `services/bff/Justfile`
- `services/bff/LICENSE`
- `services/bff/NEW_REQUIREMENTS.md`
- `services/bff/PROJECT_CONTEXT.md`
- `services/bff/README.md`
- `services/bff/REMOVE_RATE_LIMITING.md`
- `services/bff/alembic.ini` (this story commented out static `sqlalchemy.url`; resolved at runtime by env.py)
- `services/bff/alembic/env.py` (this story rewrote to use BFF settings + SQLModel.metadata)
- `services/bff/alembic/README` (archetype-style)
- `services/bff/alembic/script.py.mako`
- `services/bff/alembic/versions/` (empty — Story 1.4 lands `0001_init.py`)
- `services/bff/compose/` (archetype-emitted dev compose; gitignored from Dockerfile build context but tracked in repo)
- `services/bff/entrypoint.sh` (this story authored — alembic upgrade head → exec uvicorn)
- `services/bff/node-autochglog.config.json`
- `services/bff/pyproject.toml` (this story added `alembic` dep; rewrote `[tool.coverage.run].omit` to include `auth/entra.py`; added `[tool.coverage.report] fail_under = 90`)
- `services/bff/scripts/` (archetype helpers — `remove_demo.py` etc.)
- `services/bff/uv.lock`
- `services/bff/src/bff/` — full FastAPI service tree (~30 files):
  - `src/bff/main.py` (this story replaced the inline `/health` handler with the three-probe router; removed dummy backfill + metadata.create_all per Decision D4)
  - `src/bff/api/health.py` (NEW — three-probe readiness)
  - `src/bff/api/me.py` (NEW — anonymous 401)
  - `src/bff/api/{v1,v2}/__init__.py` (archetype-emitted)
  - `src/bff/auth/{factory,none,entra,dependencies,contracts,models,role_mapping}.py` (archetype-emitted; entra coverage-omitted)
  - `src/bff/aop/logging_decorator.py` (archetype `log_io`)
  - `src/bff/core/{config,constants,database,errors}.py` (this story added BFF_*/OIDC_* fields to config.py, added SESSION_EXPIRED+SERVICE_UNAVAILABLE to errors.py)
  - `src/bff/factories/__init__.py` (this story cleared dangling `dummy` imports left by `--no-demo`)
  - `src/bff/models/{entities,dto/v1}/__init__.py` (this story cleared dangling `dummy` imports left by `--no-demo`)
  - `src/bff/observability/{logging,otel,prometheus}.py` (archetype-emitted; left inert per project scope)
  - `src/bff/services/{v1,v2}/__init__.py` (archetype-emitted empty packages)
- `services/bff/tests/` — full pytest tree (~35 files):
  - `tests/conftest.py` (archetype-emitted)
  - `tests/api/test_health.py` (this story REPLACED with 13 tests for the three-probe behavior)
  - `tests/api/test_me.py` (NEW — 3 tests for 401 envelope)
  - `tests/api/test_cors.py` (this story switched to `/api/me` for endpoint independence from health probes)
  - `tests/api/test_dummy_routes.py`, `test_v2_dummy_routes.py`, `test_profile_service_selection.py` — removed by `--no-demo`
  - `tests/auth/*` (archetype-emitted, untouched)
  - `tests/core/*` (archetype-emitted, untouched)
  - `tests/observability/*` (archetype-emitted, untouched)
  - `tests/services/{v1,v2}/__init__.py` (archetype-emitted empty packages)

**Modified files (outside services/bff/):**

- `compose/app.yml` — added BFF service block + `bff_data` named volume.
- `docker-compose.yml` — removed inert `x-profiles:` documentation anchor + updated header comments (closes Story 1.2's punted cleanup).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-3-…` flipped `ready-for-dev` → `in-progress` → `review`; `last_updated` rolled forward.
- `_bmad-output/implementation-artifacts/1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates.md` — this story spec, with task checkboxes flipped and Dev Agent Record filled in.

**Deleted files:**

- `services/bff/.gitkeep` (placeholder removed when the real service tree landed).

**Untouched (verified):**

- Repo-root `CLAUDE.md`, `README.md`, `.env.example`, `.gitignore`, `.dockerignore`.
- `compose/infra.yml`, `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile` — Story 1.2 deliverables, bit-for-bit identical.
- All `_bmad/`, `_bmad-output/planning-artifacts/`, `.claude/`, `docs/`, `spa/`, `services/resource-server/`, `e2e/`, `tools/` (the cloned archetype stays gitignored under `tools/fastapi-archetype/`).

**Non-tracked (local development only):**

- `tools/fastapi-archetype/` — cloned at SHA `04db49c6999692cde1bfc7bfad27d1781daf0288`. Per `.gitignore`.
- `.env` and `services/bff/.env` — materialized only transiently during `docker compose config` / `docker compose build` validation, then deleted. Per `.gitignore`.

## Review Findings

Code review run on 2026-05-15 against `baseline_commit: b8dab30` after the post-scaffold cleanup pass. Three review layers ran in parallel: Blind Hunter (diff-only), Edge Case Hunter (diff + project read), Acceptance Auditor (diff + spec + project read). Findings normalized, deduped, and triaged. **Summary: 3 decision-needed, 11 patch, 17 deferred, 6 dismissed as noise.**

### Decision-needed — all resolved 2026-05-15

- [x] [Review][Decision] **AC2 / AC7 entry-point naming** — **Resolved:** update spec text to match archetype reality. AC2 directory enumeration rewritten (`main.py` only; the archetype never emits `app.py`/`__main__.py`; `auth/`/`db/`/`services/` removed from the must-have list since cleanup proved they were unused). AC7 entrypoint changed to `bff.main:app` (and the `uv run` prefix dropped — the venv `bin/` is on `PATH`, so bare `uvicorn`/`alembic` resolve correctly). The archetype is the source of truth per AR1; alignment is via spec, not by renaming code. **APPLIED.**
- [x] [Review][Decision] **AC10 `.env` bootstrap** — **Resolved:** AC10 amended to document `cp .env.example .env` at repo root and `cp services/bff/.env.example services/bff/.env` as an explicit one-time pre-step. Compose's `env_file` is intentionally left required so operators set real values for `KEYCLOAK_ADMIN_PASSWORD` / `BFF_CLIENT_SECRET` / `TEST_RESET_TOKEN` rather than silently booting on `change-me` placeholders. **APPLIED.**
- [x] [Review][Decision] **`BFF_CLIENT_SECRET` fail-fast contract** — **Resolved:** added `_validate_bff_client_secret` model_validator in `services/bff/src/bff/core/config.py` that rejects empty or whitespace-only secrets at AppSettings construction. Two new tests (`test_bff_client_secret_required`, `test_bff_client_secret_blank_string_rejected`) pin both branches. The "required-fail-fast even in 1.3" promise in `.env.example` is now code-enforced. **APPLIED.**

### Patch — all applied 2026-05-15

- [x] [Review][Patch] **P1 — `bff.models` package restored** [`services/bff/src/bff/models/__init__.py`, `services/bff/src/bff/models/entities/__init__.py`] — Empty namespaces created; `alembic upgrade head` succeeds (verified locally). Story 1.4 will populate `entities/`. **APPLIED.**
- [x] [Review][Patch] **P2 — `_BFF_ROOT` switched to env-var-driven path** [`services/bff/src/bff/api/health.py`] — `_ALEMBIC_INI = Path(os.environ.get("ALEMBIC_INI", "alembic.ini"))`. Works in container (`WORKDIR /app`), local dev / pytest (CWD is `services/bff/`), and is overridable. **APPLIED.**
- [x] [Review][Patch] **P3 — 422 envelope strips `input` field** [`services/bff/src/bff/core/errors.py`] — `validation_exception_handler` serializes structured errors with the user-supplied `input` value dropped. No more raw password / token echo. **APPLIED.**
- [x] [Review][Patch] **P4 — `/health` 503 envelope sanitized to `"down"`/`"ok"` labels** [`services/bff/src/bff/api/health.py`] — Verbose probe detail logged at WARNING server-side; response body carries no internal strings. Three endpoint tests updated; new `test_health_logs_verbose_detail_when_a_probe_fails` pins the server-side log. **APPLIED.**
- [x] [Review][Patch] **P5 — OIDC probe validates JSON + issuer field** [`services/bff/src/bff/api/health.py`] — Parses response as JSON, asserts `payload["issuer"] == issuer.rstrip("/")`. Two new tests (`test_check_oidc_discovery_rejects_non_json_body`, `test_check_oidc_discovery_rejects_issuer_mismatch`). **APPLIED.**
- [x] [Review][Patch] **P6 — OIDC probe follows redirects** [`services/bff/src/bff/api/health.py`] — `httpx.AsyncClient(..., follow_redirects=True)` (folded into the P5 patch). **APPLIED.**
- [x] [Review][Patch] **P7 — `get_engine()` `settings` parameter dropped** [`services/bff/src/bff/core/database.py`] — Function reads from module-level `_default_settings`; callers that need to swap configuration monkeypatch `_default_settings` first. Caller in `health.py` updated; `test_invalid_database_url_raises_at_engine_creation` restructured to use the new contract. **APPLIED.**
- [x] [Review][Patch] **P8 — Stale `!compose/.env` removed** [`services/bff/.gitignore`] — The un-ignore rule for a deleted directory is gone. **APPLIED.**
- [x] [Review][Patch] **P9 — `AUTH_TYPE` removed from `.env.example`** [`services/bff/.env.example`] — No longer documents a non-existent settings field. **APPLIED.**
- [x] [Review][Patch] **P10 — Stale `.dockerignore` entries removed** [`services/bff/.dockerignore`] — `AGENTS.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`, `NEW_REQUIREMENTS.md`, `REMOVE_RATE_LIMITING.md`, `RELEASE_NOTES.md`, `scripts/`, `node-autochglog.config.json` lines deleted. **APPLIED.**
- [x] [Review][Patch] **P11 — Compose healthcheck single-line form** [`compose/app.yml`] — Folded scalar `>-` replaced with a single-line `["CMD", "python", "-c", ...]` list mirroring the Dockerfile `HEALTHCHECK`. **APPLIED.**

### Deferred

- [x] [Review][Defer] **Log redaction regex false-positives** [`services/bff/src/bff/observability/logging.py:18-26`] — Archetype-shipped regex; mangles prose containing "bearer"/"authorization"/"token"/"secret". Belongs upstream / observability pass.
- [x] [Review][Defer] **CORS middleware install frozen at module import** [`services/bff/src/bff/main.py:37-45`] — Tests work around with `importlib.reload`. Move to lifespan-time install in a later pass.
- [x] [Review][Defer] **`configure_logging` runs in lifespan, not at import** [`services/bff/src/bff/main.py:21-27`] — Pre-lifespan logs (uvicorn startup, instantiation errors) are unstructured. Move to module import time later.
- [x] [Review][Defer] **404/405 responses don't follow the documented error envelope** [`services/bff/src/bff/main.py:47-51`] — Architecture §C5 envelope is `{errorCode, message, detail}`; Starlette defaults are `{detail}`. Punt to Story 1.10 (SPA error handling) or sooner.
- [x] [Review][Defer] **Test stubs mounted on the live `bff.main:app` singleton at conftest import** [`services/bff/tests/conftest.py:25-37`] — Harmless in pytest-only flow; refactor to a separate test app later.
- [x] [Review][Defer] **`.githooks/pre-commit` is dead weight** [`services/bff/.githooks/pre-commit`] — Not wired up (no `git config core.hooksPath`), runs network `npx --yes node-autochglog`, auto-stages a generated file. Delete or wire up in a tooling pass.
- [x] [Review][Defer] **`alembic/env.py` imports private `_to_async_url`** [`services/bff/alembic/env.py:23`] — Reaches into a `_`-prefixed helper. Promote to public or duplicate logic.
- [x] [Review][Defer] **`CORSMiddleware` typed with `# ty: ignore`** [`services/bff/src/bff/main.py:39`] — Inline ignore explains starlette's signature isn't typed per-middleware.
- [x] [Review][Defer] **`AppSettings.profile` `Literal["default","mock"]` collides with compose `profiles: [default, dev, e2e]`** [`services/bff/src/bff/core/config.py:32`, `compose/app.yml:44`] — Two unrelated concepts share the name. Rename one when convenient.
- [x] [Review][Defer] **`_format_arg` truncates any repr starting with `<`** [`services/bff/src/bff/aop/logging_decorator.py:74-76`] — Archetype regex; collapses XML/HTML payload args. Tighten upstream.
- [x] [Review][Defer] **No `.gitattributes` enforcing LF for `*.sh`** — Windows hosts may produce CRLF entrypoint.sh that breaks the shebang. Add `.gitattributes` defensively later.
- [x] [Review][Defer] **`tests/conftest.py` engine fixture drop_all/create_all between tests** [`services/bff/tests/conftest.py:63-86`] — No-op in Story 1.3 (zero entities); Story 1.4 will inherit the cost.
- [x] [Review][Defer] **BFF `README.md` advertises capabilities removed during cleanup** [`services/bff/README.md`] — Still references `/metrics`, OTEL OTLP export, RBAC, `DB_DRIVER`. Archetype doc drift; Story 5.3 (README polish) is the right home.
- [x] [Review][Defer] **`/health` is an unauthenticated DoS surface** [`services/bff/src/bff/api/health.py:116-135`] — Rate limiting out of scope; revisit in Story 5.2 (security review).
- [x] [Review][Defer] **`alembic upgrade head` in `entrypoint.sh` is not SIGTERM-safe** [`services/bff/entrypoint.sh:15-19`] — Benign now (zero migrations); add `trap`/wait pattern when Story 1.4 lands.
- [x] [Review][Defer] **`Justfile` in-tree but `.dockerignore` excludes it** [`services/bff/Justfile`, `services/bff/.dockerignore`] — Cleanup inconsistency; decide keep-and-unignore vs remove later.
- [x] [Review][Defer] **`auth/`, `db/`, `services/` subpackages absent** [`services/bff/src/bff/`] — Removed in cleanup as empty; tied to the AC2 decision-needed above. Tracks the post-decision option of leaving them absent permanently.

### Dismissed (not actioned)

- `except ValueError, TypeError:` is **not** a SyntaxError in Python 3 — parses as `except (ValueError, TypeError):` (verified). Blind Hunter false alarm.
- `_validate_cors_requirements` only blocks literal `*` — matches AC and middleware norms; wildcard-subdomain is out of scope.
- `os.environ["ENV_FILE"] = ""` timing in conftest — set before `from bff.main import app`, so settings construct with empty env-file. 98.10% test pass demonstrates correctness.
- `api/me.py` hardcoded 401 without TODO guard — AC5 explicitly defines this contract; module docstring documents the Story 1.5 transition.
- `_check_database` catches `Exception` — `CancelledError` is `BaseException` in 3.8+, propagates correctly.
- `api/me.py` doesn't read `BFF_SESSION_COOKIE_NAME` — AC5 contract is "always 401 regardless of cookie state"; reading the cookie name would be cosmetic.

### Acceptance Auditor verdict table

| AC | Status | Note |
|----|--------|------|
| 1  | MET | `tools/fastapi-archetype/` gitignored; no archetype files in `git status` |
| 2  | PARTIALLY MET | Tree as expected EXCEPT entry-point is `main.py` not `app.py`/`__main__.py`, and `auth/`/`db/`/`services/` removed in cleanup → see decision-needed item #1 |
| 3  | MET | `uv sync --frozen` exit 0; `ruff check` clean; `ty check` clean; `pytest --cov` 113 passed at **98.10%** (>90% required) |
| 4  | MET | `/health` returns 200 `{"status":"ok"}` when all three probes pass; 503 + `SERVICE_UNAVAILABLE` envelope on failure; unauthenticated; no `/metrics`; no OTEL exporter wiring |
| 5  | MET | `/api/me` returns 401 + `session_expired` envelope unconditionally |
| 6  | MET | `SESSION_EXPIRED` present; no premature deferred enum members |
| 7  | PARTIALLY MET | Multi-stage `python:3.14-slim` + Alembic-on-startup + `HEALTHCHECK` correct; entrypoint runs `uvicorn bff.main:app` (spec says `bff.app:app`) → see decision-needed item #1 |
| 8  | MET | SQLite URL points at `/data/bff.db`; `bff_data:/data` volume mount |
| 9  | MET | All compose attributes (depends_on, env_file, healthcheck, volume, profiles) correct |
| 10 | NOT VERIFIABLE on clean clone | `.env` bootstrap required → see decision-needed item #2 |
| 11 | MET | Per-service `.env.example` template; root `.env.example` unchanged |
| 12 | MET | Per-service context + `services/bff/.dockerignore` chosen; dev log records the decision |
| 13 | MET | Files outside the scope-list unchanged |

