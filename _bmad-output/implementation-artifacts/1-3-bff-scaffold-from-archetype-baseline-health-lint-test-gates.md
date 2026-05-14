---
status: ready-for-dev
story_key: 1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates
epic: 1
prerequisites: 1-1 (done), 1-2 (backlog — see "Cross-story dependency" in Dev Notes)
---

# Story 1.3: BFF scaffold from archetype + baseline health + lint/test gates

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer working on the BFF,
I want the BFF scaffolded from the `fastapi-archetype` with the archetype's lint/test/typecheck gates green and a working `GET /health` and anonymous `GET /api/me` endpoint,
so that I have a clean foundation that already meets the archetype's >90% coverage target before later stories layer on auth, books, and SPA wiring.

## Acceptance Criteria

1. **Archetype is cloned (gitignored) at the documented path.** `tools/fastapi-archetype/` exists locally (cloned from `https://github.com/tommaso-meledina/fastapi-archetype.git`) and is matched by the existing `.gitignore` rule `tools/fastapi-archetype/`. No archetype files appear in `git status`.

2. **The BFF is scaffolded via the archetype's `build_template.py`.** Running
   `python tools/fastapi-archetype/scripts/build_template.py -n bff -o services/bff --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"`
   produces the archetype's standard layout under `services/bff/`: `pyproject.toml`, `uv.lock`, `alembic.ini`, `alembic/` (env.py, script.py.mako, versions/), `src/bff/` (with `app.py`, `__main__.py`, `api/`, `services/`, `auth/`, `core/`, `aop/`, `db/`), `tests/` mirroring `src/bff/`, `Dockerfile`, `.env.example`, the `ErrorCode` enum, and the `log_io` AOP decorator. The pre-existing `services/bff/.gitkeep` is removed.

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
   - uses a small shell entrypoint that runs `uv run alembic upgrade head` and then `exec uv run uvicorn bff.app:app --host 0.0.0.0 --port 8000` (per architecture §"Operational Details / Migrations on startup"),
   - declares a `HEALTHCHECK` that calls `GET /health` (any HTTP client available in the slim image is acceptable; if `curl` is not present, use `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"` or install `curl`).

8. **The named volume `bff_data` mounts at `/data`.** Per AR6, the BFF's SQLite file lives in a Docker named volume; the BFF database URL in `services/bff/.env` resolves to a file under `/data` (e.g., `sqlite+aiosqlite:////data/bff.db` — matching the existing repo-root `.env.example`).

9. **BFF service is defined in `compose/app.yml`.** The service:
   - has `depends_on: { keycloak: { condition: service_healthy } }`,
   - has `env_file: services/bff/.env` (path relative to the compose project root; `services/bff/.env` is gitignored — see AC #11),
   - has its own healthcheck calling `GET /health`,
   - mounts the `bff_data` named volume at `/data`,
   - declares `profiles: [default, dev, e2e]` so the inert top-level `x-profiles` documentation anchor in `docker-compose.yml` no longer carries the only mention (the anchor may be deleted in this story or left to be cleaned up later — dev judgment).

10. **`docker compose config` validates cleanly** from the repo root with the BFF service present, with **no** errors and **no** warnings beyond Compose's standard informational notes. The composed output includes the BFF service block. If Story 1.2 has not landed Keycloak yet, see "Cross-story dependency" in Dev Notes — coordinate ordering rather than referencing a non-existent service.

11. **Per-service `.env` strategy is documented and applied.** `services/bff/.env.example` (emitted by the archetype scaffold) is preserved as a per-service template, but the BFF service in compose reads from `services/bff/.env` (gitignored). The root-level `.env.example` (Story 1.1) remains the canonical AR29 enumeration; no env-var divergence between root `.env.example` and `services/bff/.env.example` for the variables the BFF consumes (`BFF_CLIENT_SECRET`, `BFF_DATABASE_URL`, `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`, `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`). Update `.gitignore` if needed so `services/bff/.env` is ignored but `services/bff/.env.example` is tracked.

12. **`.dockerignore` strategy is resolved (deferred-work D4).** Either:
    - The BFF image is built with `context: services/bff` and a `services/bff/.dockerignore` is authored, or
    - The BFF image is built with the repo root as `context:` and the existing root `.dockerignore` is amended to keep build context minimal.
    Document the choice in a one-paragraph note in the dev log. The recommended approach (per the architecture's per-service deployable boundary) is **per-service context** with a per-service `.dockerignore`.

13. **Pre-existing repo state is preserved.** Files outside `services/bff/`, `compose/app.yml`, `.gitignore`, `.dockerignore`, and the BMAD bookkeeping files (`sprint-status.yaml`, this story file) are unchanged. Specifically: `CLAUDE.md`, the root `.env.example`, `docker-compose.yml`'s `include:` block, `compose/infra.yml`, and the Story 1.1 `README.md` are untouched (the BFF setup note in README belongs in Story 5.3, not here).

## Tasks / Subtasks

- [ ] **Task 1 — Clone the archetype** (AC: #1)
  - [ ] `git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype` (executed locally only; archetype dir is gitignored).
  - [ ] Verify `git status --short` shows no archetype files leaking through (`tools/fastapi-archetype/` should be matched by the existing `.gitignore` rule).

- [ ] **Task 2 — Scaffold the BFF** (AC: #2)
  - [ ] Remove `services/bff/.gitkeep` (the directory is now becoming a real service tree).
  - [ ] Run `python tools/fastapi-archetype/scripts/build_template.py -n bff -o services/bff --description "BMAD_books Backend-for-Frontend (OAuth client, books domain)"`. (Use `python`, not `python3` — per project `CLAUDE.md`.)
  - [ ] If `build_template.py` refuses a non-empty output dir, remove the `.gitkeep` first and re-run; do not pass any flag that overwrites unrelated files.
  - [ ] Inspect the generated tree and confirm the archetype directories from architecture §"Complete Project Directory Structure" lines 882–933 are present: `src/bff/{app.py, __main__.py, api/, services/, auth/, core/, aop/, db/}`, `tests/{api/, services/, auth/, core/, aop/, db/, conftest.py}`, `alembic/{env.py, script.py.mako, versions/}`, `alembic.ini`, `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`.

- [ ] **Task 3 — Verify archetype gates green out of the box** (AC: #3)
  - [ ] `cd services/bff && uv sync --frozen` → 0.
  - [ ] `uv run ruff check` → 0, no findings.
  - [ ] `uv run ty` → 0, no type errors.
  - [ ] `uv run pytest --cov` → 0, coverage > 90% for `src/bff/`. Capture the coverage percentage in the dev log.
  - [ ] If any gate is **not** green on a fresh archetype scaffold: do **not** silence it. File the discrepancy in the dev log and either (a) apply the smallest possible fix in `src/bff/` if the failure is in our new code, or (b) flag as an archetype defect upstream and pin the archetype to a known-good revision in `tools/`.

- [ ] **Task 4 — Implement the `GET /health` readiness probes** (AC: #4)
  - [ ] Replace (or extend) the archetype's default `/health` handler with the three-check version: DB reachable (`SELECT 1`), Alembic at head, OIDC discovery doc fetchable.
  - [ ] Route lives where the archetype puts health (commonly `src/bff/api/health.py` or registered in `src/bff/app.py`; follow archetype convention rather than inventing a location).
  - [ ] The OIDC discovery fetch uses `httpx.AsyncClient` with the BFF→Keycloak timeouts from architecture §C6 (5s connect, 10s read; **no retries** — per FR-ERROR-01, healthchecks must not paper over startup failures).
  - [ ] On any probe failure: return 503 with the archetype error envelope; map to an existing `ErrorCode` (do not invent a new one solely for health — if none fits, raise the archetype's generic "service unavailable" code or extend the enum with a single new value and justify it in the dev log).
  - [ ] **No `/metrics` endpoint, no OTEL exporter wiring.** If the archetype scaffold emits Prometheus or OTEL boilerplate, it remains inert — do not register a collector, do not expose `/metrics`.
  - [ ] Tests in `tests/api/test_health.py` cover: success (all probes green), DB failure, Alembic-not-at-head, OIDC discovery 5xx/timeout/network-error. Use `httpx.MockTransport` or the archetype's HTTP-mocking pattern; do not start a real Keycloak.

- [ ] **Task 5 — Implement anonymous `GET /api/me`** (AC: #5, #6)
  - [ ] Register a router for `/api/me` at the BFF root (path `/api/me`, not `/v1/api/me` — `/api/me` is non-versioned per architecture §C1).
  - [ ] Implementation for this story: if **no session cookie** is presented, return **401** with `{"errorCode": "session_expired", "message": "...", "detail": null}`. Read the cookie name from `BFF_SESSION_COOKIE_NAME` env (pydantic-settings).
  - [ ] If a session cookie **is** present: still return 401 / `session_expired` for this story. Authenticated `/api/me` is Story 1.5's deliverable; do not implement session lookup here (the `sessions` table does not exist until Story 1.4's migration lands).
  - [ ] Ensure `ErrorCode.SESSION_EXPIRED = "session_expired"` exists in `src/bff/core/error_codes.py`. If the archetype already provides an equivalent member, reuse it; otherwise add it.
  - [ ] Tests in `tests/api/test_me.py` cover: no cookie → 401 envelope with exact `errorCode`; cookie-present-but-no-session → also 401 (validates this story's "still 401" contract).

- [ ] **Task 6 — Author the BFF `Dockerfile`** (AC: #7, #12)
  - [ ] Start from the archetype's `Dockerfile` if one is emitted; otherwise hand-author a multi-stage build:
    - **Build stage** (`python:3.14-slim`): `uv` installed, `uv sync --frozen` runs, source copied.
    - **Final stage** (`python:3.14-slim`): runtime deps only via `uv sync --frozen --no-dev`, source copied, `entrypoint.sh` chmod'd, default `CMD` is the entrypoint.
  - [ ] `entrypoint.sh` (committed under `services/bff/` per architecture line 1334):
    ```sh
    #!/bin/sh
    set -e
    uv run alembic upgrade head
    exec uv run uvicorn bff.app:app --host 0.0.0.0 --port 8000
    ```
  - [ ] `HEALTHCHECK` directive on the final stage hits `GET http://localhost:8000/health` (use a stdlib `python -c "..."` one-liner if `curl` is not installed in the slim image, or install `curl` — pick one and document in dev log).
  - [ ] Decide context strategy (D4 carryover): per-service `context: services/bff` with a per-service `services/bff/.dockerignore` is recommended. Write the `.dockerignore` to exclude `tests/`, `.venv/`, `.pytest_cache/`, `__pycache__/`, `.coverage`, `*.sqlite*`, `.env`, `alembic/versions/__pycache__/`. Document the choice in the dev log.

- [ ] **Task 7 — Add the BFF service to `compose/app.yml`** (AC: #8, #9, #10, #11)
  - [ ] Add a `bff` service: `build: { context: services/bff }` (per Task 6's context decision), `env_file: services/bff/.env`, `volumes: [bff_data:/data]`, `ports: ["8000:8000"]` (so the host can reach OIDC redirects in later stories), `depends_on: { keycloak: { condition: service_healthy } }`, `profiles: [default, dev, e2e]`, `healthcheck:` calling `GET /health` (the same probe as the Dockerfile's `HEALTHCHECK`, since compose's healthcheck overrides the image one).
  - [ ] Declare the `bff_data` named volume in `compose/app.yml`'s top-level `volumes:` block.
  - [ ] Author `services/bff/.env.example` so it mirrors exactly the AR29 vars the BFF consumes (see AC #11 list). The archetype-emitted `services/bff/.env.example` is the starting point — reconcile its contents with the root-level `.env.example` (no new vars, no divergent placeholders).
  - [ ] Update `.gitignore` if needed: `services/bff/.env` must be gitignored; `services/bff/.env.example` must be tracked. Carry forward Story 1.1's pattern: `**/.env` + `!**/.env.example` already covers this — but verify; if not, broaden the whitelist (per D5 in `deferred-work.md`).
  - [ ] The inert top-level `x-profiles: [default, dev, e2e]` in `docker-compose.yml` may be removed in this story (now redundant — the BFF service carries the profile names), or left alone for Story 1.8 / 3.1 / 1.2 to clean up later. Dev judgment.
  - [ ] Run `docker compose config` from the repo root. Confirm exit 0 with the `bff` service rendered in the output. Capture the output in the dev log.

- [ ] **Task 8 — Coordinate with Story 1.2 (cross-story dependency)** (AC: #10)
  - [ ] Story 1.2 (Keycloak realm-as-code + compose service) is in `backlog` per sprint-status. `docker compose config` will **fail** at the `depends_on: keycloak` reference if `keycloak` is not defined in any included compose file. Options, in order of preference:
    1. **Confirm Story 1.2 has been completed first.** If it has, the `keycloak` service is in `compose/infra.yml` and AC #10 passes naturally.
    2. **Land Story 1.3's code without the `depends_on: keycloak` block**, leave a `TODO(story-1.2)` comment, and update `compose/app.yml` once Story 1.2 ships. Document this decision and update the AC #9 status as partially deferred to Story 1.2's merge.
    3. **Stub a minimal `keycloak` service** in `compose/infra.yml` whose only job is to make `docker compose config` validate — but **do not** do this if it would create rework when Story 1.2 lands. This is the least preferred option.
  - [ ] Pick one of the three; document the choice with rationale in the dev log. If option 2 is chosen, raise a defer item to `deferred-work.md` referencing AC #9/#10 reactivation in Story 1.2.

- [ ] **Task 9 — Run the full gate sequence end-to-end** (AC: #3, #10)
  - [ ] From `services/bff/`: `uv sync --frozen && uv run ruff check && uv run ty && uv run pytest --cov`. All 0-exit; coverage > 90%.
  - [ ] From repo root: `docker compose config`. Exit 0, BFF service present in output.
  - [ ] (Optional but valuable) `docker compose build bff` should produce an image with no warnings of concern. Do **not** require `docker compose up` to succeed for AC verification — runtime smoke depends on Keycloak (Story 1.2).
  - [ ] Capture every command's stdout/return code in the dev log.

- [ ] **Task 10 — Bookkeeping** (AC: #13)
  - [ ] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates` from `ready-for-dev` → `in-progress` at story start, then to `review` once the dev workflow completes (matches Story 1.1's pattern).
  - [ ] Verify `CLAUDE.md`, root `.env.example`, `docker-compose.yml` `include:` block (apart from the optional `x-profiles` cleanup in Task 7), `compose/infra.yml`, and `README.md` are unchanged except where Task 7 / 8 explicitly touch them.

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

### Cross-story dependency: Story 1.2

Story 1.2 (Keycloak realm-as-code + compose service) is in `backlog` per `sprint-status.yaml`. The BFF service in `compose/app.yml` declares `depends_on: { keycloak: { condition: service_healthy } }`, which Compose validates at config time — referencing a non-existent service will fail `docker compose config`.

**The natural ordering** (per architecture §"Decision Impact Analysis / Implementation Sequence" lines 519–520, and per the sprint-status order: 1-2 sits before 1-3) is **Story 1.2 lands first, then Story 1.3**. If that is the case, AC #10 passes naturally with `keycloak` resolved.

**If Story 1.3 is implemented before Story 1.2** (e.g., parallel work), Task 8 records the three coordination options. **The preferred mitigation** is to omit the `depends_on: keycloak` block from this story and defer it (option 2 in Task 8), with a `TODO(story-1.2)` comment in `compose/app.yml`. Re-add the dependency when Story 1.2 merges. Record as `deferred-work.md` item if chosen.

**Runtime health-check note.** Even with Story 1.2 in place, the runtime verification of `GET /health` returning 200 requires Keycloak to be up and the OIDC discovery doc reachable. The `/health` *code* and its unit tests (Task 4) are in this story's scope; runtime smoke is gated by Story 1.2 — that is acceptable. The Story 1.3 ACs verify the *behavior contract* of `/health` via unit tests with mocked dependencies.

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

From `_bmad-output/implementation-artifacts/deferred-work.md` (Story 1.1 review surfaced these):

- **D1** — `.env.example` SQLite paths assume in-container `/data`. **This story addresses D1** by ensuring the BFF runs in the container (where `/data` is the named volume mount). If a developer wants to run the BFF on the host (`dev` profile per architecture §I2), they will need to override `BFF_DATABASE_URL` in a per-host `.env` to point at a host-side path. Document this in the dev log; do **not** invent a second `.env.example`.
- **D2** — OIDC URLs use the Docker-internal hostname `keycloak`. **Out of this story's scope** — D2 is owned by Stories 1.4–1.5 (BFF cookie/OIDC plugin needs the browser-facing redirect topology). For Story 1.3, the `/health` discovery fetch happens **server-side from the BFF container**, so the `keycloak:8080` hostname resolves correctly. Do not change `OIDC_ISSUER_URL`.
- **D3** — `change-me` placeholder credentials accepted at runtime. **Out of this story's scope.** D3 lands when `BFF_CLIENT_SECRET` is actually consumed by the OIDC plugin (Stories 1.4–1.5). Story 1.3's pydantic-settings config declares the var as required but does not enforce the "must not equal `change-me` in non-dev profiles" check.
- **D4** — Per-service `.dockerignore` strategy. **This story resolves D4** (Task 6, Task 7) by choosing per-service `context: services/bff` with a per-service `services/bff/.dockerignore`. Document the decision.
- **D5** — `.gitignore` whitelist for per-service env templates. **Story 1.3 must verify** that `services/bff/.env.example` is tracked while `services/bff/.env` is ignored. Story 1.1's pattern (`**/.env` + `!.env.example`) currently whitelists the **root** `.env.example` only — confirm whether it also whitelists `services/bff/.env.example` (it does NOT under that exact pattern). Broaden the whitelist (e.g., add `!**/.env.example`) and document.

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
- **Do not add `depends_on:` blocks for services that have not been defined.** If Story 1.2 is not yet merged, omit the `depends_on: keycloak` and TODO it (Task 8 option 2).
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

### Previous story intelligence (from 1.1)

Story 1.1 is **done** at commit `3ec36be` ("finished story 1.1"), baselined at `215d84e`. Relevant takeaways:

- **Scope discipline was the dominant pattern.** The dev agent for 1.1 deliberately refused to scaffold service contents, run `build_template.py`, or invent env vars beyond AR29. Story 1.3 should adopt the same discipline in the opposite direction: scaffold the BFF in full, but do **not** drift into 1.4/1.5/1.6/1.7 work.
- **Three deferred items now land in Story 1.3** (D1 partially, D4 fully, D5 fully) — see "Known deferred items relevant to this story" above. Story 1.1's review noted these explicitly; closing them here is expected and tracked.
- **`x-profiles: [default, dev, e2e]` was added as an inert documentation anchor** in `docker-compose.yml`. Story 1.1's Dev Notes called out that this becomes redundant churn as soon as a real service carries `profiles: [...]`. Story 1.3 adds the BFF with real profile membership, so the anchor can be removed (or left for later cleanup — see Task 7).
- **`tools/` is tracked via `.gitkeep`; only `tools/fastapi-archetype/` is gitignored.** Story 1.3 keeps this convention: the archetype clones into `tools/fastapi-archetype/` and remains untracked.
- **CLAUDE.md is preserved verbatim.** Use `python` (not `python3`) — `build_template.py` is invoked as `python tools/.../build_template.py ...`.
- **`docker compose config` validation captured in the dev log** is the pattern Story 1.1 established. Carry it forward: AC #10's verification log goes into the Dev Agent Record.
- **Sprint-status bookkeeping pattern**: flip `ready-for-dev` → `in-progress` at story start, `in-progress` → `review` at hand-off to `code-review`. Story 1.1 set this precedent; Story 1.3 mirrors it.

### Git intelligence (recent commits)

```
3ec36be finished story 1.1
8f27b32 feat: implement story 1.1 — repo scaffold + compose skeleton
215d84e feat: story 1.1
489796f feat: implementation readiness
e0227e0 feat: debriefed and created architecture
```

- Last three commits all relate to Story 1.1. No code outside `_bmad-output/`, root scaffold files, and the per-directory `.gitkeep`s has landed yet.
- No other branches with in-progress BFF work — the BFF tree is a clean slate.
- No `services/bff/` files exist beyond `.gitkeep`; no commit will need to be rebased.

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
- [Source: `_bmad-output/implementation-artifacts/1-1-repo-scaffold-compose-skeleton.md`] — previous story patterns, deferred-work hand-offs (D1/D4/D5 land here).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D1, D4, D5] — items this story is expected to resolve or partially address.
- [Source: `CLAUDE.md` at repo root] — project convention: invoke Python as `python`, never `python3`.
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — backend archetype mandate, observability carve-out.

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
