---
status: ready-for-dev
story_key: 3-1-rs-scaffold-from-archetype-baseline-health-rs-in-compose-default-dev
epic: 3
prerequisites: epic-1 (done — BFF + Keycloak + SPA + Playwright harness merged); 1-3 (done — archetype-scaffold pattern established); 1-12/1-14 (done — `compose/app.e2e.yml` overlay pattern and BFF multi-stage Dockerfile in main)
note_on_epic_order: Epic 2 (books) is still backlog at the time this story is created. The user has elected to land Epic 3 ahead of Epic 2. This is sequencing-only; nothing in Story 3.1 depends on Epic 2 deliverables. The RS only depends on Epic 1 (Keycloak realm + BFF infra patterns).
specLoopIteration: 1
---

# Story 3.1: RS scaffold from archetype + baseline health + RS in compose (default/dev)

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer working on the Resource Server,
I want the RS scaffolded from `fastapi-archetype` with the archetype's lint/test/typecheck gates green, a baseline `GET /health` that probes DB + Alembic-at-head + JWKS reachability, and the RS running in the compose `default` and `dev` profiles,
so that subsequent Epic 3 / Epic 4 stories can build the JWKS bearer auth, scope enforcement, `reading_speeds` schema, and `/v1/reading-speed` / `/v1/estimate` endpoints on a working RS service with health-check-gated startup ordering already proved.

## Acceptance Criteria

1. **Archetype is cloned (gitignored) at the documented path.** `tools/fastapi-archetype/` exists locally (cloned from `https://github.com/tommaso-meledina/fastapi-archetype.git`) and is matched by the existing `.gitignore` rule `tools/fastapi-archetype/`. No archetype files appear in `git status`. *(Story 1.3 cloned this already at SHA `04db49c6999692cde1bfc7bfad27d1781daf0288`; if the clone is still present locally, reuse it — do not re-clone unnecessarily. If absent, clone fresh and capture the SHA in the dev log; pin to the same SHA as Story 1.3 if upstream `main` has drifted, for reproducibility with the BFF scaffold.)*

2. **The RS is scaffolded via the archetype's `build_template.py`.** Running
   `python tools/fastapi-archetype/scripts/build_template.py -n resource-server -o services --description "BMAD_books Resource Server (reading speed, estimate)" --author "BMAD_books contributors" --email "noreply@example.com" --no-demo`
   (NB: `-o` is the **parent** dir per the empirical Story 1.3 fix, not `services/resource-server`; cookiecutter requires the output dir to not already exist) produces the archetype's standard layout under `services/resource-server/`: `pyproject.toml`, `uv.lock`, `alembic.ini`, `alembic/` (`env.py`, `script.py.mako`, `versions/`), `src/resource_server/` with `main.py` as the FastAPI factory + entrypoint, `api/`, `core/`, `aop/`, `observability/`, `models/`, `tests/` mirroring `src/resource_server/`, `Dockerfile`, `.env.example`, the `ErrorCode` enum, and the `log_io` AOP decorator.

   The pre-existing `services/resource-server/.gitkeep` is removed before scaffolding (cookiecutter refuses non-empty output dirs; the parent-dir `-o` flag means `services/resource-server/` must not exist before the run). The archetype emits `main.py` only — there is no `app.py` / `__main__.py` (per the Story 1.3 review's resolution of decision-needed #1; AR1 makes the archetype the source of truth, so the import path is `resource_server.main:app`).

3. **Dependency install, lint, type-check, and tests pass cleanly.** From `services/resource-server/`:
   - `uv sync --frozen` exits 0.
   - `uv run ruff check` exits 0 with **zero** findings.
   - `uv run ruff format --check` exits 0.
   - `uv run ty check` exits 0 with **zero** type errors.
   - `uv run pytest --cov` exits 0 and reports coverage **strictly greater than 90%** for `src/resource_server/` (the archetype's configured threshold, declared in `[tool.coverage.report] fail_under`).
   - If the archetype-emitted `auth/entra.py` (Azure-AD bearer; ~150 LOC, ~38% covered out of the box on the BFF — same module ships in the RS scaffold) drags coverage below 90%, omit it from `[tool.coverage.run].omit` with a documenting comment, mirroring the Story 1.3 BFF carve-out (Story 1.3 dev log line 455–462). Story 3.2 will likely **delete** `entra.py` outright when it lands `oidc_bearer.py`.

4. **`GET /health` is implemented with the three documented readiness probes.** The endpoint:
   - returns **200** with a small JSON body (e.g., `{"status": "ok"}`) once **all three** of the following are true at request time:
     (a) the RS database is reachable (a trivial `SELECT 1` against the SQLite engine succeeds),
     (b) Alembic reports the database is at the head revision (with zero migrations defined both head and current are `None`, which trivially satisfies the check until Story 3.3 lands the first migration — mirrors the BFF's transition between Stories 1.3 and 1.4),
     (c) the JWKS endpoint at `OIDC_JWKS_URL` is fetchable over HTTP and returns a JWKS-shaped JSON body — a 2xx response with a top-level `keys` array (any length ≥ 0 is acceptable; this is a liveness probe, not a key-rotation probe). Like the BFF's `/health` (Story 1.3 + P5/P6 patches), the JWKS check (i) honors AR19 timeouts (5s connect, 10s read, zero retries — health probes must not paper over startup failures per FR-ERROR-01), (ii) follows 3xx redirects, (iii) does NOT validate that the keys are usable for token verification (that is the territory of `PyJWKClient` in Story 3.2). **Architectural rationale:** per architecture §"Operational Details / Health checks" line 1327, the RS's readiness depends on DB reachability + Alembic at head + **JWKS reachability** — explicitly JWKS, *not* the full OIDC discovery doc that the BFF probes (the RS never calls the OAuth flow endpoints, only `OIDC_JWKS_URL`).
   - returns **503** with the archetype error envelope (`{"errorCode": "...", "message": "...", "detail": null}`) when any probe fails. Map to the same `ErrorCode.SERVICE_UNAVAILABLE = "service_unavailable"` (HTTP 503) that the BFF added in Story 1.3 — declare it in this story if the archetype doesn't already provide an equivalent. Detail field in the response body is **sanitized** to per-probe `"ok"`/`"down"` labels (mirroring BFF Story 1.3 review patch P4); rich diagnostic strings (exception messages, paths, hostnames) are logged at WARNING server-side only — never echoed to the unauthenticated caller.
   - is **unauthenticated** — no session, no bearer required (per architecture §"Operational Details" — health endpoints are always-on).
   - has **no observability instrumentation** (no `/metrics`, no OTEL exporter wiring; the archetype's OTEL/Prometheus emission is left inert per the 2026-05-14 sprint-change cut and per AR1 user-mandate note). If the scaffold emits `observability/otel.py` / `observability/prometheus.py` boilerplate, leave it in place but ensure `OTEL_EXPORT_ENABLED=false` (or equivalent archetype flag) is the default so no exporter connects, and `/metrics` is not exposed on the FastAPI app — same approach as Story 1.3 BFF (dev log line 525).

5. **No `/api/me` equivalent on the RS.** Per architecture line 1124 ("SPA ↔ Resource Server: **never**"), the RS does not serve browser-facing identity. There is no `/api/me`, no `/auth/login`, no `/auth/callback`, no `/auth/logout`. The HTTP surface for this story is **`GET /health` only**; the `/v1/*` endpoints arrive in Stories 3.3 (`/v1/reading-speed`), 3.4 (`/v1/test/reset`), and 4.1 (`/v1/estimate`).

6. **`ErrorCode` enum is extended only with the project-specific values that the RS needs *at this story's surface*.** At minimum: `SERVICE_UNAVAILABLE = "service_unavailable"` (HTTP 503) is present in `src/resource_server/core/error_codes.py` (or `errors.py` — match the archetype's file name as Story 1.3 found it: the BFF's is `core/errors.py`). The rest of the architecture §C5 enumeration (`RESOURCE_SERVER_UNAVAILABLE`, `READING_SPEED_UNSET`, `SESSION_EXPIRED`, `FORBIDDEN_SCOPE`, `INVALID_INPUT`, `BOOK_NOT_FOUND`, `AUTH_STATE_INVALID`, `CSRF_INVALID`) is **deferred** to the stories that first consume each value. On the RS specifically:
   - `READING_SPEED_UNSET` (412) — Story 3.3 (the GET 412 path).
   - `FORBIDDEN_SCOPE` (403) — Story 3.2 (`require_scope` dependency factory).
   - `SESSION_EXPIRED` (401) — Story 3.2 (JWT validation failures map to 401 with this code per the epics file lines 1184–1197).
   - `INVALID_INPUT` (422) — Story 3.3 (PUT body validation).
   - `RESOURCE_SERVER_UNAVAILABLE` (503) — **BFF-only** (it never appears on the RS; the RS is the resource that becomes unavailable, it doesn't surface this code).
   - `BOOK_NOT_FOUND`, `AUTH_STATE_INVALID`, `CSRF_INVALID` — BFF-only (the RS has no books, no PKCE, no CSRF).

7. **`services/resource-server/Dockerfile` is multi-stage on `python:3.14-slim` with an Alembic-on-startup entrypoint.** The final stage:
   - bases on `python:3.14-slim`,
   - uses `uv` (mounted from `ghcr.io/astral-sh/uv:0.10.7` — match the BFF's pinned version unless upstream advances and is verified; see Story 1.3 BFF `Dockerfile` lines 18 and 28–37 for the cache-mounted `uv sync --locked` pattern),
   - installs runtime deps via `uv sync --locked --no-dev --no-editable`,
   - uses a small shell entrypoint (`services/resource-server/entrypoint.sh`) that runs `alembic upgrade head` (resolved via the venv `bin/` on `PATH`, no `uv run` prefix needed at runtime — per the Story 1.3 review's decision-needed #1) and then `exec uvicorn resource_server.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"`,
   - creates `/data` with `app:app` ownership (so SQLite can write the `rs.db` file there regardless of host UID mapping — mirrors BFF `Dockerfile` lines 45–46),
   - declares a `HEALTHCHECK` that probes `GET http://localhost:8000/health` using the stdlib (`python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)"`) — no `curl` install per the BFF precedent (Story 1.3 dev log line 343–344).
   - **No Node builder stage.** Unlike the BFF Dockerfile (Story 1.14), the RS has no SPA to bake — its image is Python-only, single-language, multi-stage on `python:3.14-slim` only. The RS does **not** serve any static assets.

8. **The named volume `rs_data` mounts at `/data`.** Per AR6 and architecture §I5, the RS's SQLite file lives in a Docker named volume separate from the BFF's `bff_data`. The RS database URL in `services/resource-server/.env` resolves to a file under `/data` (`sqlite+aiosqlite:////data/rs.db`, matching the existing repo-root `.env.example` line for `RS_DATABASE_URL`). Declare the `rs_data` named volume in `compose/app.yml`'s top-level `volumes:` block (alongside the existing `bff_data`).

9. **RS service is defined in `compose/app.yml`.** The service:
   - has `build: { context: .., dockerfile: services/resource-server/Dockerfile }` (root context, mirroring the BFF's post-1.14 build context; the root `.dockerignore` from Story 1.14 already excludes non-RS service trees so build context stays minimal — see AC #12),
   - has `container_name: resource-server`,
   - has `env_file: ../services/resource-server/.env` (path relative to `compose/app.yml`; the per-service `.env` is gitignored — see AC #11),
   - mounts the `rs_data` named volume at `/data`,
   - has `depends_on: { keycloak: { condition: service_healthy } }` — the RS depends on Keycloak so it can fetch JWKS at startup (per AR28 / architecture line 1327),
   - has its own compose-level healthcheck calling `GET /health` (single-line `["CMD", "python", "-c", ...]` list form — mirrors the BFF service per Story 1.3 review patch P11; folded-scalar YAML form is forbidden),
   - declares `profiles: [default, dev]` (the `e2e` profile addition lands in Story 3.6 alongside the `killRs`/`startRs`/`resetState` helper extensions),
   - does **NOT** publish a port to the host — the RS is internal-only (BFF reaches it via Docker DNS at `http://resource-server:8000`); only the BFF container exposes a user-facing port (per architecture §F3 + §I6). *(Contrast with the BFF service block which publishes `"8000:8000"` per Story 1.3 for the browser OIDC redirect.)*
   - sets `restart: unless-stopped` (matches BFF).

10. **The BFF's existing `depends_on` is NOT changed.** Per the epics file Story 3.1 AC4 and architecture §"Operational Details / Health checks and `depends_on` ordering": the BFF continues to depend only on Keycloak. The BFF does NOT gain `depends_on: { resource-server: { condition: service_healthy } }` — when the RS is down, the BFF must surface `errorCode: resource_server_unavailable` honestly (per FR-ERROR-01 / J6), not refuse to start. Verify `compose/app.yml`'s BFF block is byte-for-byte unchanged in its `depends_on` field after this story's edits (the only BFF-block changes permitted are incidental and only if a separate review surfaces them — none are expected).

11. **Per-service `.env` strategy is documented and applied.** `services/resource-server/.env.example` (emitted by the archetype scaffold) is rewritten to mirror the AR29 enumeration restricted to the vars the RS actually consumes:
    - `RS_DATABASE_URL` — used by the RS's `db/session_factory.py`; defaults to `sqlite+aiosqlite:////data/rs.db`.
    - `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE` — used by `/health` (Story 3.1 — JWKS reachability) and by Story 3.2's JWT validation. Declared **required-fail-fast** at AppSettings construction (mirrors the BFF's `BFF_CLIENT_SECRET` validator added by Story 1.3 review's decision-needed #3); the RS's `OIDC_AUDIENCE` MUST equal `bmad-books-resource-server` (the value Story 1.2's realm-as-code mints into the access token's `aud` claim — see Story 1.5's D2 resolution).
    - `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN` — declared with defaults `false` / `change-me`; consumed by Story 3.4's `POST /v1/test/reset`.
    - **Do NOT** declare `OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET`, `BFF_BASE_URL`, `BFF_DATABASE_URL`, `BFF_SESSION_COOKIE_*`, `BFF_CSRF_COOKIE_*` — those are BFF-only and have no consumer on the RS.

    Keep the root-level `.env.example` (Story 1.1, Story 1.2-edited) **unchanged** — its `RS_DATABASE_URL` line (currently `sqlite+aiosqlite:////data/rs.db`) and the OIDC quartet already cover what the RS reads. No new AR29 vars are introduced by this story. Update `.gitignore` only if needed so `services/resource-server/.env` is ignored but `services/resource-server/.env.example` is tracked — the existing repo-root pattern `**/.env` + `!**/.env.example` (from Story 1.1) already does this; verify, don't reinvent.

12. **`.dockerignore` strategy mirrors the BFF's post-1.14 choice.** Per Story 1.14, the BFF Dockerfile uses **root build context** so its Node builder stage can `COPY spa/`. The RS has no SPA dependency, so technically per-service context (`context: services/resource-server`) would also work — but for consistency with the existing repo posture, use **root context** + the existing root `.dockerignore` (which already excludes `services/bff/tests/`, `services/bff/.ruff_cache/`, etc.). Amend the root `.dockerignore` to add equivalent RS-specific exclusions (`services/resource-server/tests/`, `services/resource-server/.ruff_cache/`, `services/resource-server/.githooks/` if the archetype emits one). The per-service `services/resource-server/.dockerignore` may exist (the archetype emits one) but it is **not consulted** when the build context is the repo root — keep it in place for documentation parity with `services/bff/` (which has both files per Story 1.3 / 1.14). Document the choice in the dev log.

13. **`docker compose config` validates cleanly** from the repo root with the RS service present (default profile), with **no** errors and **no** warnings beyond Compose's standard informational notes. As established by Story 1.3 review's decision-needed #2: before `docker compose config` will run, a one-time bootstrap is required — `cp .env.example .env` at the repo root, `cp services/bff/.env.example services/bff/.env`, and (new for this story) `cp services/resource-server/.env.example services/resource-server/.env`. All three target files are gitignored; the bootstrap forces operators to set real values rather than booting on `change-me` placeholders. The composed output includes the `resource-server` service block, the `rs_data` named volume, and resolves the `keycloak` reference (Story 1.2) and the `bff` reference (Story 1.3) cleanly. Capture the validated output in the dev log.

14. **Pre-existing repo state is preserved.** Files outside `services/resource-server/`, `compose/app.yml`, `.dockerignore`, `.gitignore` (only if a verifiable adjustment is needed — none expected), and the BMAD bookkeeping files (`sprint-status.yaml`, this story file, `deferred-work.md` only for new defers) are unchanged. Specifically: `CLAUDE.md`, the root `README.md`, the root `.env.example`, `docker-compose.yml`'s `include:` block, `compose/infra.yml`, `compose/app.e2e.yml`, `keycloak/*`, `services/bff/**` (every file unchanged), `spa/**` (every file unchanged), `e2e/**` (every file unchanged) are bit-for-bit identical to their pre-story state.

## Tasks / Subtasks

- [ ] **Task 1 — Clone or refresh the archetype** (AC: #1)
  - [ ] Check if `tools/fastapi-archetype/` already exists from Story 1.3. If present, run `git -C tools/fastapi-archetype rev-parse HEAD` and capture the SHA; verify it matches `04db49c6999692cde1bfc7bfad27d1781daf0288` (Story 1.3's pinned SHA). If it does, skip the clone. If it diverged, decide explicitly: keep current SHA (and capture it in the dev log) OR `git -C tools/fastapi-archetype reset --hard 04db49c` to align with the BFF scaffold's archetype version. **Recommended:** align to `04db49c` for reproducibility — both backend services scaffolded from the same archetype revision.
  - [ ] If absent: `git clone https://github.com/tommaso-meledina/fastapi-archetype.git tools/fastapi-archetype && git -C tools/fastapi-archetype checkout 04db49c6999692cde1bfc7bfad27d1781daf0288`.
  - [ ] Verify `git status --short` shows no archetype files leaking through.

- [ ] **Task 2 — Scaffold the RS** (AC: #2)
  - [ ] Remove `services/resource-server/.gitkeep` (the directory is now becoming a real service tree).
  - [ ] Remove `services/resource-server/` itself (cookiecutter refuses non-empty output dirs and the `-o services` parent-dir flag means `services/resource-server/` must not exist before the run — same workaround Story 1.3 used).
  - [ ] If cookiecutter is not already installed in the dev's `uv` tool dir from Story 1.3: `uv tool install cookiecutter`.
  - [ ] Run: `python tools/fastapi-archetype/scripts/build_template.py -n resource-server -o services --description "BMAD_books Resource Server (reading speed, estimate)" --author "BMAD_books contributors" --email "noreply@example.com" --no-demo`. (Use `python`, not `python3` — per project `CLAUDE.md`.)
  - [ ] Inspect the generated tree. Expected (per Story 1.3 empirical findings): `src/resource_server/main.py` (not `app.py`), `src/resource_server/{api,core,aop,observability,models}/`, `tests/` mirroring source, `alembic/`, `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`, archetype dev-docs (`AGENTS.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`, `NEW_REQUIREMENTS.md`, `REMOVE_RATE_LIMITING.md`, `RELEASE_NOTES.md`, `Justfile`, etc.).
  - [ ] **Clean up `--no-demo` dangling imports** (known upstream defect in `remove_demo.py` — Story 1.3 hit this; the `--no-demo` flag leaves stale `from … import dummy` references in `main.py`, `models/entities/__init__.py`, `models/dto/v1/__init__.py`, `factories/__init__.py`). Fix in the **scaffolded output**, NOT in `tools/fastapi-archetype/`.
  - [ ] **Decision: empty subpackages.** Story 1.3's resolution (decision-needed #1) was to remove `auth/`, `db/`, `services/` empty subpackages from the BFF scaffold and recreate them when their owning story lands. Mirror that here — but note that this story does NOT need any of `auth/`, `db/`, `services/`, `api/` populated beyond `api/health.py`. The dev may keep or remove the empty packages — match the BFF's resolved state (removed). Story 3.2 will recreate `auth/` (for `oidc_bearer.py`); Story 3.3 will recreate `db/models/` (for `reading_speed.py`) and `services/` (for `reading_speed_service.py`).

- [ ] **Task 3 — Verify archetype gates green out of the box** (AC: #3)
  - [ ] `cd services/resource-server && uv sync --frozen` → 0. (If `--frozen` fails on the fresh scaffold: file a defect against the archetype; do NOT run `uv lock` to regenerate.)
  - [ ] `uv run ruff check` → 0, no findings.
  - [ ] `uv run ruff format --check` → 0.
  - [ ] `uv run ty check` → 0, no type errors.
  - [ ] `uv run pytest --cov` → 0, coverage > 90% for `src/resource_server/`. Capture the percentage in the dev log.
  - [ ] If coverage lands below 90% because of `auth/entra.py` (Story 1.3 BFF hit this exact case at 83% pre-omit / 96.15% post-omit): add `auth/entra.py` to `[tool.coverage.run].omit` in `pyproject.toml` with a multi-line comment explaining the rationale (Story 3.2 will replace this module with `oidc_bearer.py`). Re-run `pytest --cov` and confirm > 90%.
  - [ ] If any gate fails on the fresh scaffold for a reason **other than** the entra coverage carve-out, do NOT silence it: file the discrepancy in the dev log and either apply the smallest possible fix in `src/resource_server/` (if the failure is project-side) or pin the archetype to a known-good SHA in `tools/` (if it's archetype-side).

- [ ] **Task 4 — Implement the `GET /health` readiness probes** (AC: #4, #6)
  - [ ] Author `src/resource_server/api/health.py` mirroring the BFF's three-probe pattern (`services/bff/src/bff/api/health.py` lines 51–186 are the reference implementation; copy the structure, swap the OIDC-discovery probe for a JWKS probe).
  - [ ] Three async probe functions returning `tuple[bool, str]`:
    - `_check_database(engine)` — `SELECT 1` against the engine. Identical to BFF.
    - `_check_alembic_at_head(engine)` — uses `ScriptDirectory.from_config(AlembicConfig(str(_ALEMBIC_INI))).get_current_head()` compared with `MigrationContext.configure(conn).get_current_revision()` over an async connection via `run_sync`. Identical to BFF. With zero migrations until Story 3.3, both are `None` ⇒ at-head is True (acceptable).
    - `_check_jwks(cfg)` — `httpx.AsyncClient(timeout=Timeout(connect=cfg.oidc_jwks_connect_timeout, read=cfg.oidc_jwks_read_timeout), follow_redirects=True)` GETs `cfg.oidc_jwks_url`. Returns `(False, detail)` on connection error, non-2xx, non-JSON body, body that is not a JSON object, or body where `keys` is missing / not a list. Returns `(True, "")` on a 2xx response with a `{"keys": [...]}` JSON object (length-0 or longer — this is liveness, not key-rotation). Honors AR19 timeouts (5s/10s) and **zero retries**.
  - [ ] The `health()` handler orchestrates the three probes (in parallel via `asyncio.gather` is fine, or sequentially — match the BFF's sequential approach for code symmetry / simpler debugging). Returns 200 `{"status": "ok"}` when all three are `True`; otherwise returns 503 with envelope `{"errorCode": "service_unavailable", "message": "...", "detail": {"database": "ok"|"down", "alembic": "ok"|"down", "jwks": "ok"|"down"}}` — sanitized labels only. Rich per-probe `detail_str` is logged at WARNING server-side (`logger.warning("health probe failed: db=%s alembic=%s jwks=%s", ...)`) — never echoed.
  - [ ] `_ALEMBIC_INI = Path(os.environ.get("ALEMBIC_INI", "alembic.ini"))` — env-driven path so the probe works in the container (`WORKDIR /app`), local dev / pytest (CWD is `services/resource-server/`), and is overridable in tests (mirrors BFF Story 1.3 review patch P2).
  - [ ] Register the router on the app: `app.include_router(health_router)`. If the archetype-emitted `src/resource_server/main.py` already mounts a `/health` handler, **replace** the body of that handler (or replace the router) — do not register a second one.
  - [ ] **Architecture mandate:** the JWKS probe is **liveness**, not configuration-correctness. It does NOT validate that the JWKS' `kid`s match what tokens will carry, does NOT validate that `OIDC_ISSUER_URL` is byte-equal to any field, does NOT assert `OIDC_AUDIENCE` makes sense. Those are Story 3.2's territory. The `/health` ask is narrow: "is Keycloak alive and serving its JWKS document?" Do not couple `/health` to Keycloak's frontend-URL configuration (the same lesson Story 1.3 learned with D45 on the BFF's OIDC discovery probe).
  - [ ] **No `/metrics` endpoint, no OTEL exporter wiring** — same posture as Story 1.3 BFF. If the archetype emits `observability/otel.py` / `observability/prometheus.py`, leave them in place but ensure the relevant default flag (`OTEL_EXPORT_ENABLED=false` or archetype equivalent) keeps them inert.
  - [ ] Tests in `tests/api/test_health.py` cover (minimum):
    1. All three probes succeed → 200 `{"status": "ok"}`.
    2. DB unreachable → 503 with sanitized envelope.
    3. Alembic not at head (e.g., script head ≠ current revision) → 503.
    4. JWKS returns 5xx → 503.
    5. JWKS times out (`httpx.TimeoutException`) → 503.
    6. JWKS returns non-JSON body → 503.
    7. JWKS returns JSON but not an object (e.g., `[1,2,3]`) → 503.
    8. JWKS returns `{}` (object without `keys` field) → 503.
    9. JWKS returns `{"keys": []}` → **200** (empty array is acceptable; this is liveness, not key validity).
    10. JWKS returns `{"keys": [<one key>]}` → 200.
    11. Server-side WARNING log is emitted when a probe fails (mirrors BFF Story 1.3 review patch P4's `test_health_logs_verbose_detail_when_a_probe_fails`).
  - [ ] Mock the JWKS HTTP call via `httpx.MockTransport`. Mock DB / Alembic state by monkeypatching the helpers (or using a fresh in-memory SQLite that is deliberately not at head). Do **not** spin up a real Keycloak in unit tests (AR33 — synthetic IdP pattern; the synthetic-IdP harness itself lands in Story 3.2).

- [ ] **Task 5 — Author the RS `Dockerfile` and `entrypoint.sh`** (AC: #7)
  - [ ] Start from the archetype's emitted `Dockerfile` if it ships one; otherwise hand-author a multi-stage build mirroring the BFF's post-1.14 structure but without the Node builder stage:
    - **Stage 0 (builder, `python:3.14-slim`):** mount `uv` from `ghcr.io/astral-sh/uv:0.10.7`. `WORKDIR /app`. Set `UV_COMPILE_BYTECODE=1`, `UV_LINK_MODE=copy`, `UV_PYTHON_DOWNLOADS=never`. With root build context: bind-mount `services/resource-server/uv.lock`, `services/resource-server/pyproject.toml`, `services/resource-server/.python-version`; run `uv sync --locked --no-install-project --no-dev --no-editable` with cache mount. Then `COPY services/resource-server/ /app/` and re-run `uv sync --locked --no-dev --no-editable`. (Reference: `services/bff/Dockerfile` lines 16–37.)
    - **Stage 1 (final, `python:3.14-slim`):** `groupadd --system app && useradd --system --gid app app && mkdir -p /data && chown app:app /data`. `COPY --from=builder --chown=app:app /app/.venv /app/.venv`, `COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini`, `COPY --from=builder --chown=app:app /app/alembic /app/alembic`, `COPY --from=builder --chown=app:app /app/entrypoint.sh /app/entrypoint.sh`. `RUN chmod +x /app/entrypoint.sh`. `WORKDIR /app`. Set `ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 WEB_CONCURRENCY=1`. `USER app`. `EXPOSE 8000`.
  - [ ] `HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=15s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else 1)" || exit 1` — stdlib probe, no `curl` install (Story 1.3 / 1.14 precedent).
  - [ ] `ENTRYPOINT ["/app/entrypoint.sh"]`.
  - [ ] Author `services/resource-server/entrypoint.sh`:
    ```sh
    #!/bin/sh
    # Resource Server container entrypoint.
    # 1) alembic upgrade head — schema at head BEFORE uvicorn starts (per AR28).
    #    Story 3.1 ships zero migrations; this is a no-op until Story 3.3 lands
    #    the first ReadingSpeed migration.
    # 2) exec replaces the shell so SIGTERM reaches uvicorn cleanly.
    set -e
    alembic upgrade head
    exec uvicorn resource_server.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
    ```
    Mirrors `services/bff/entrypoint.sh` verbatim except for the module path. The venv `bin/` is on `PATH` so bare `alembic` and `uvicorn` resolve correctly — no `uv run` prefix needed (Story 1.3 decision-needed #1 resolved this).
  - [ ] Add `*.sh text eol=lf` to a `services/resource-server/.gitattributes` file — defends against Windows CRLF breaking the shebang (D22 from Story 1.3's deferred items; addressing it preemptively here costs nothing and matches the Story 1.3 dev log's note to add it later).

- [ ] **Task 6 — Add the RS service to `compose/app.yml` + named volume + RS `.env.example`** (AC: #8, #9, #10, #11, #13)
  - [ ] Append a `resource-server` service block to `compose/app.yml` (after the existing `bff` block, before the `playwright` block):
    ```yaml
    resource-server:
      build:
        context: ..
        dockerfile: services/resource-server/Dockerfile
      container_name: resource-server
      env_file:
        - ../services/resource-server/.env
      volumes:
        - rs_data:/data
      depends_on:
        keycloak:
          condition: service_healthy
      healthcheck:
        test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else 1)"]
        interval: 10s
        timeout: 5s
        retries: 30
        start_period: 30s
      profiles: [default, dev]
      restart: unless-stopped
    ```
    **Do NOT add a `ports:` block** — the RS is internal-only (architecture §F3 + §I6; the BFF reaches it at `http://resource-server:8000` over Docker DNS). **Do NOT add `e2e` to the profiles list** — that addition is Story 3.6's job, paired with the `ENABLE_TEST_RESET=true` env overlay (Story 3.4's endpoint).
  - [ ] Add `rs_data: {}` to `compose/app.yml`'s top-level `volumes:` block (next to the existing `bff_data: {}`). Annotate with a one-line comment mirroring the existing `bff_data` annotation.
  - [ ] **Do NOT modify the existing `bff` service block.** AC #10 is unambiguous: BFF `depends_on` does not change. The `bff` block in `compose/app.yml` should be byte-for-byte identical after this story's edits (run `git diff compose/app.yml` and inspect — only the `resource-server` addition + the `rs_data` volume line should appear).
  - [ ] Rewrite `services/resource-server/.env.example` (overwriting the archetype's emission) with the AR29 subset the RS consumes — see AC #11. Add the archetype meta lines from the BFF template as a reference (APP_NAME, DEBUG, LOG_LEVEL, LOG_MODE, PROFILE, ROOT_PATH) since the archetype's `AppSettings` reads them. **Mirror `services/bff/.env.example`'s comment header style** (one-paragraph rationale at top + per-section dividers).
  - [ ] Verify the repo-root `.gitignore` still has `**/.env` and `!**/.env.example` (carried forward from Story 1.1). No changes expected. The pattern correctly tracks `services/resource-server/.env.example` while ignoring `services/resource-server/.env`.
  - [ ] Amend the root `.dockerignore` to add: `services/resource-server/tests/`, `services/resource-server/.ruff_cache/`, `services/resource-server/.githooks/` (if emitted) — mirror the existing BFF-specific exclusions at the bottom of the file.
  - [ ] **Bootstrap pre-step for `docker compose config` validation** (mirrors Story 1.3 AC #10): `cp .env.example .env` (if not already from Story 1.3), `cp services/bff/.env.example services/bff/.env` (if not already), `cp services/resource-server/.env.example services/resource-server/.env`. All three target files are gitignored. Then `docker compose config` from repo root — confirm exit 0 with the `resource-server` service rendered, the `rs_data` volume present, and the existing `bff` + `keycloak` blocks unchanged. Capture the output in the dev log.
  - [ ] Clean up the three `.env` files after validation (`rm .env services/bff/.env services/resource-server/.env`) — they are all gitignored anyway but removing them keeps the working tree pristine.

- [ ] **Task 7 — Confirm BFF and Keycloak integration surface is intact** (AC: #10, #14)
  - [ ] Sanity-check `compose/infra.yml` (Story 1.2): the `keycloak` service exists with `KC_HOSTNAME=localhost`, `KC_HOSTNAME_STRICT=false`, `KC_HEALTH_ENABLED=true`, healthcheck on `/health/ready`. `depends_on: { keycloak: { condition: service_healthy } }` from the RS service resolves cleanly.
  - [ ] Sanity-check the OIDC env var values consumed by `/health`: `OIDC_JWKS_URL=http://keycloak:8080/realms/bmad-books/protocol/openid-connect/certs` (per Story 1.2's realm). From inside the RS container, this resolves via Docker DNS once Keycloak's healthcheck is green — `depends_on: service_healthy` gates RS startup until that is true.
  - [ ] Confirm `compose/app.yml`'s BFF service block is unchanged. Run `git diff -- compose/app.yml` and verify the only added lines are within the new `resource-server` service block + the new `rs_data:` volume line.
  - [ ] **Optional, recommended:** `docker compose --profile default up -d keycloak` and wait for the healthcheck to flip green; then `curl -fsS http://localhost:8080/realms/bmad-books/protocol/openid-connect/certs` returns a 200 JSON document with a `keys` array. This is exactly what the RS's `/health` probe relies on. If it works from the host, it works from the RS container over Docker DNS.
  - [ ] If anything above is **not** as described, escalate before continuing — do not paper over a Story 1.2/1.3 regression here.

- [ ] **Task 8 — Run the full gate sequence end-to-end** (AC: #3, #13)
  - [ ] From `services/resource-server/`: `uv sync --frozen && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest --cov`. All 0-exit; coverage > 90%.
  - [ ] From repo root: `docker compose config` (after the bootstrap pre-step from Task 6). Exit 0; `resource-server` service present in output.
  - [ ] **Optional but valuable:** `docker compose build resource-server` should produce an image with no warnings of concern. Do **not** require `docker compose up` to succeed for AC verification — runtime smoke depends on Keycloak (Story 1.2) and exercises Story 3.2's territory.
  - [ ] (Optional, recommended) `docker compose --profile default up keycloak resource-server` and verify the RS container reaches the healthy state — i.e., its `/health` probe goes green once Keycloak's JWKS is reachable. If desired, `curl http://localhost:8000/health` will **not** work from the host (the RS does not publish a port); instead, `docker exec resource-server python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read())"` exercises the probe from inside the container.
  - [ ] Capture every command's stdout/return code in the dev log.

- [ ] **Task 9 — Bookkeeping** (AC: #14)
  - [ ] Update `_bmad-output/implementation-artifacts/sprint-status.yaml`: flip `3-1-rs-scaffold-from-archetype-baseline-health-rs-in-compose-default-dev` from `ready-for-dev` → `in-progress` at story start, then to `review` once the dev workflow completes (matches Story 1.3's pattern). Update `last_updated` with the date + a one-line note. Verify `epic-3` is `in-progress` (the create-story workflow already flipped it from `backlog` when this story was created).
  - [ ] If new deferred items surface during code review, add them to `_bmad-output/implementation-artifacts/deferred-work.md` under a new `## Deferred from: code review of 3-1-rs-scaffold-...` section. Use unique D-numbers continuing from the highest existing D-number (the current ceiling is D53 from Story 1.14 — see deferred-work.md tail).
  - [ ] Verify `CLAUDE.md`, root `.env.example`, root `README.md`, `docker-compose.yml`'s `include:` block, `compose/infra.yml`, `compose/app.e2e.yml`, `keycloak/*`, `services/bff/**`, `spa/**`, `e2e/**` are unchanged.

## Dev Notes

### What this story is — and is not

**This story stands up the RS service tree from the archetype and makes the archetype's gates green.** It also adds one HTTP-level surface — `GET /health` with the three readiness probes (DB, Alembic at head, JWKS reachable). That is the entire HTTP surface in scope.

**Explicitly NOT in scope (each is a downstream story):**

- **No JWKS-based JWT validation, no `oidc_bearer` plugin, no scope enforcement.** Those are Story 3.2. The `auth/` directory may exist (per archetype layout) or may be absent post-cleanup — but it does not yet contain `oidc_bearer.py`.
- **No `reading_speeds` table, no `ReadingSpeed` SQLModel, no `/v1/reading-speed` GET/PUT.** Those are Story 3.3. The Alembic `versions/` directory exists empty (or with whatever the archetype emits); the first real migration is Story 3.3's.
- **No `/v1/test/reset` endpoint.** Story 3.4. The env vars `ENABLE_TEST_RESET` and `TEST_RESET_TOKEN` are declared in `.env.example` (and validated as required by AppSettings if the archetype's pattern requires it) but not consumed.
- **No `ResourceServerClient` on the BFF.** Story 3.5.
- **No `SettingsView` on the SPA.** Story 3.5.
- **No `/v1/estimate` POST endpoint.** Story 4.1.
- **No observability.** Per the 2026-05-14 sprint-change cut + AR1 note: no `/metrics` endpoint, no OTEL exporter wiring, no Prometheus scrape. If the archetype emits `observability/` boilerplate, leave it inert (same as Story 1.3 BFF — dev log line 525).
- **No `ErrorCode` values beyond `SERVICE_UNAVAILABLE`** for this story. Adding the full architecture §C5 set now would create dead code; let each downstream story add the value it first consumes (per Story 1.3's anti-pattern guidance — proven sound across Epic 1).
- **No `e2e` compose profile entry, no `ENABLE_TEST_RESET=true` overlay, no `killRs`/`startRs` helper implementations.** Those are Story 3.6 (E2E spec + helpers + e2e profile updates). This story's `profiles: [default, dev]` is intentional.
- **No `ports:` block on the RS service.** The RS is internal-only — only the BFF container publishes a user-facing port.
- **No SPA serving on the RS.** Unlike the BFF (which serves the SPA bundle per AR24 / Story 1.14), the RS is JSON-API-only.

### Story 1.2 / 1.3 / 1.14 integration surface (already merged)

**Story 1.2 (done)** — `compose/infra.yml` defines Keycloak with the realm import, `KC_HOSTNAME=localhost`, healthcheck on `/health/ready` (port 9000). `keycloak/realm-bmad-books.json` defines realm `bmad-books`, client `bmad-books-bff` with PKCE, client scopes `reading-speed:read` / `reading-speed:write` (granted to BFF), audience mapper `bmad-books-resource-server` on the access token, users `testuser` / `freshuser`. The RS's `OIDC_AUDIENCE=bmad-books-resource-server` is the value that Story 3.2 will validate against `aud` on every JWT.

**Story 1.3 (done)** — BFF scaffolded from the same archetype (pin SHA `04db49c6...`). This story should pin to the **same** archetype SHA — both services scaffolded from the same revision keeps `pyproject.toml` versions, `ErrorCode` enum surface, and `log_io` AOP decorator identical, which makes future cross-service drift easier to spot. The BFF lives at `services/bff/`; the RS will live at `services/resource-server/`. The two are independently deployable (each has its own `pyproject.toml`, `Dockerfile`, `uv.lock`, `tests/`) and **never cross-import** (architecture §"Architectural Boundaries" — "no cross-service Python imports"). The "synthetic-IdP test harness" pattern the archetype ships in `tests/auth/` works for both services; Story 3.2 will extend it for the RS's `oidc_bearer` mode.

**Story 1.14 (done)** — BFF Dockerfile became multi-stage with a Node builder stage (Stage 0) that compiles the SPA. The build context shifted to repo root (`context: ..` in compose) and the root `.dockerignore` was amended. **The RS Dockerfile uses the same root-context posture for consistency** (AC #12), even though the RS has no SPA dependency. This keeps the two service Dockerfiles structurally aligned: same `python:3.14-slim` base, same builder/runtime split, same `uv` pin, same entrypoint + healthcheck pattern.

**Runtime `/health` probe path** (per AC #4 c) is `http://keycloak:8080/realms/bmad-books/protocol/openid-connect/certs` — i.e., `${OIDC_JWKS_URL}` verbatim. From inside the RS container, this resolves via Docker DNS once Keycloak's healthcheck is green; the RS's `depends_on: service_healthy` gate ensures the RS doesn't start until that is true. **The JWKS document body** contents are only minimally validated (top-level JSON object with a `keys` array) — Story 3.2's `PyJWKClient` is where the actual key parsing and signature validation lives.

**Why JWKS, not OIDC discovery?** The BFF's `/health` probes the OIDC discovery doc (`/.well-known/openid-configuration`) because the BFF is an OAuth client that uses the full discovery surface — `/authorize`, `/token`, `/end_session`, `/revocation` (all listed in the discovery doc). The RS is an OAuth **resource server** — it never visits `/authorize` or `/token`. The only Keycloak endpoint it actually reads is the JWKS. Probing JWKS directly is both narrower (less surface area to break) and more honest (it asserts the actual dependency, not a proxy for it). Architecture line 1327 makes this explicit: "RS: `/health` returns 200 once DB reachable, Alembic at head, and **JWKS fetchable**."

### Archetype mandate (AR1)

Both backend services are built on `github.com/tommaso-meledina/fastapi-archetype` per user memory `[[project-bmad-books-backend-archetype]]`. For this story specifically:

- **Pin to the same archetype SHA as Story 1.3** (`04db49c6999692cde1bfc7bfad27d1781daf0288`) unless there's a verified upstream reason to advance. Reproducibility across BFF + RS = future-you reading commit history will not be confused.
- **Do not edit `tools/fastapi-archetype/`.** The directory is gitignored. If an archetype defect blocks progress (Story 1.3 hit `--no-demo` leaving dangling imports), patch the **scaffolded output** under `services/resource-server/`, not the archetype itself.
- **Trust the archetype's choices.** Python 3.14, FastAPI, SQLModel, uv, Ruff, ty, pytest, the `{errorCode, message, detail}` envelope, the `log_io` AOP decorator, and the `none`/`entra` auth plugins are archetype-provided. Story 3.2 will extend `entra` into `oidc_bearer`; Story 3.1 leaves them alone (the entra coverage carve-out — AC #3 — is the only allowed touch).

### Architecture-prescribed RS anatomy

Reference: architecture lines 954–1007. The dev agent should see this layout after Task 2 (modulo the Story 1.3 empirical findings — `main.py` not `app.py`, empty subpackages removed by cleanup):

```
services/resource-server/
├── pyproject.toml                          # archetype-emitted; Python 3.14, ruff, ty, pytest config
├── uv.lock                                 # archetype-emitted
├── alembic.ini                             # archetype-emitted (Story 1.3 found this needs `sqlalchemy.url` commented out; env.py resolves at runtime)
├── alembic/
│   ├── env.py                              # archetype-emitted; this story rewrites to read RS_DATABASE_URL via cfg
│   ├── script.py.mako
│   └── versions/                           # empty until Story 3.3's 0001_init
├── Dockerfile                              # this story authors / extends the multi-stage build (no Node stage)
├── entrypoint.sh                           # this story authors — Alembic + uvicorn
├── .env.example                            # this story rewrites to RS-specific AR29 subset
├── .dockerignore                           # archetype-emitted; left in place for documentation parity (root .dockerignore is what compose actually consults)
├── .gitattributes                          # NEW — `*.sh text eol=lf` (D22 preempted)
└── src/resource_server/
    ├── __init__.py
    ├── main.py                             # archetype-emitted; FastAPI factory + router registration + uvicorn entry
    ├── api/
    │   ├── __init__.py
    │   └── health.py                       # this story authors — three-probe readiness (DB + Alembic + JWKS)
    ├── core/
    │   ├── config.py                       # archetype-emitted; ensure pydantic-settings reads RS_DATABASE_URL, OIDC_* (this story)
    │   ├── error_codes.py (or errors.py)   # this story adds SERVICE_UNAVAILABLE if missing
    │   ├── exceptions.py                   # archetype-emitted
    │   ├── error_handlers.py               # archetype-emitted
    │   └── di.py                           # archetype-emitted
    ├── aop/
    │   └── logging.py                      # archetype-emitted (log_io decorator)
    └── observability/                      # archetype-emitted; left inert (no /metrics, no OTEL exporter)
```

Architecture additionally enumerates `auth/`, `db/`, `services/`, `models/` subpackages — these are the destinations Stories 3.2–4.1 will write into. For Story 3.1, follow Story 1.3's resolution: keep or remove empty subpackages per dev judgment; do not author files in them.

Tests under `services/resource-server/tests/` mirror `src/resource_server/`:

```
tests/
├── conftest.py                             # archetype-emitted; in-memory SQLite + TestClient
├── api/
│   └── test_health.py                      # this story authors — 11+ cases (success + each failure mode)
├── core/, aop/, observability/             # archetype-emitted scaffolding; passes coverage threshold
└── fixtures/                               # archetype-emitted helpers
```

### `pydantic-settings` config (AR29 → RS)

The RS's `core/config.py` (pydantic-settings) must declare and read the AR29 subset it consumes:

- `RS_DATABASE_URL` — used by `db/session_factory.py`; must be a valid SQLAlchemy async URL (the existing root `.env.example` ships `sqlite+aiosqlite:////data/rs.db`, which works in the container with the `rs_data` volume mounted at `/data`).
- `OIDC_ISSUER_URL` — used by Story 3.2's JWT validation. **Declared required-fail-fast** at AppSettings construction (mirrors BFF `BFF_CLIENT_SECRET` validator pattern from Story 1.3 review's decision-needed #3).
- `OIDC_JWKS_URL` — used by **`/health`** (this story) and by Story 3.2. **Declared required-fail-fast.**
- `OIDC_AUDIENCE` — used by Story 3.2. **Declared required-fail-fast.** The expected value is `bmad-books-resource-server` (Story 1.2's audience mapper); the RS does not enforce that string match at AppSettings level — Story 3.2's JWT validation does.
- `ENABLE_TEST_RESET` — Story 3.4. Default `false`; required-fail-fast not appropriate (the field is a feature flag, not a secret). Type `bool` via pydantic-settings.
- `TEST_RESET_TOKEN` — Story 3.4. Default `change-me`; same fail-fast posture as the BFF (the route is not mounted when `ENABLE_TEST_RESET=false`, so a weak default is acceptable until Story 3.4 wires the actual gate; mirrors the BFF's `bff.api.test_reset.register_test_reset_router` pattern).
- **Do NOT declare:** `OIDC_CLIENT_ID`, `BFF_CLIENT_SECRET`, `BFF_BASE_URL`, `BFF_DATABASE_URL`, `BFF_SESSION_COOKIE_*`, `BFF_CSRF_COOKIE_*`. None of these have an RS consumer.

The archetype's default pattern (Story 1.3 confirmed) is to fail at AppSettings construction if a `required` field is missing. Don't weaken this. The `services/resource-server/.env.example` documents every var so `cp .env.example .env` is the local boot flow.

### Known deferred items relevant to this story

From `_bmad-output/implementation-artifacts/deferred-work.md`:

- **D1 (Story 1.1)** — `.env.example` SQLite paths assume in-container `/data`. **This story addresses the RS half of D1** (`RS_DATABASE_URL`) by ensuring the RS runs in the container where `/data` is the `rs_data` named-volume mount. Dev-profile host runs would require a per-host override; document in `services/resource-server/.env.example` comments mirroring the BFF's note.
- **D4 (Story 1.1)** — Per-service `.dockerignore` strategy. The BFF half closed in Story 1.3 (per-service context + per-service file), then **shifted** in Story 1.14 to root context + root `.dockerignore` when the SPA build stage was added. **This story closes the RS half of D4** by aligning the RS Dockerfile to the post-1.14 root-context pattern (AC #12) — both backend services now build from the same root context with the same `.dockerignore`. Document the decision in the dev log.
- **D5 (Story 1.1)** — Already-closed `**/.env` + `!**/.env.example` pattern. Verify it still works for `services/resource-server/.env.example`; no broadening needed (Story 1.3 confirmed the pattern is correct).
- **D22 (Story 1.3 review)** — No `.gitattributes` enforcing LF for `*.sh`. The BFF deferred this; this story **preempts** D22 for the RS by shipping `services/resource-server/.gitattributes` with `*.sh text eol=lf` (Task 5). Cheap and right.
- **D14/D15/D16/D17/D18/D19/D20/D21/D23 (Story 1.3 review)** — Archetype-shipped issues (log redaction false-positives, CORS middleware install timing, 404/405 envelope drift, `_to_async_url` private import, `AppSettings.profile` name collision, etc.). All inherit into the RS scaffold and remain deferred to a coordinated archetype-upstream pass. Story 3.1 should NOT attempt to fix them (the same defects already deferred in the BFF should not be selectively fixed only in the RS — that creates cross-service drift).
- **D49–D53 (Story 1.14 review)** — BFF-specific SPA serving items; do not bite the RS.

**No new deferred items expected from Story 3.1.** The story is intentionally narrow (scaffold + `/health` + compose wiring), and the patterns are all proven by Story 1.3.

### Anti-patterns to avoid

- **Do not run `build_template.py` more than once** against `services/resource-server/`. The archetype's emissions are not idempotent. If you need to re-run, first `rm -rf services/resource-server/` (after committing any of-this-story additions to a branch backup) and start fresh.
- **Do not delete archetype-emitted code paths to "improve coverage."** Coverage > 90% is the gate; the archetype passes it on a fresh scaffold modulo the `entra.py` carve-out (Story 1.3 dev log line 455). Add the carve-out, not deletions.
- **Do not introduce `print()` debug output.** Use `logger = logging.getLogger(__name__)` per architecture §"Communication Patterns / Error handling (backend services)". The archetype's `log_io` AOP decorator handles service-method I/O; do not double-decorate.
- **Do not raise `HTTPException` directly from handlers.** Define a domain exception (or reuse an archetype-provided one) and let `core/error_handlers.py` map it to the envelope. For `/health`, returning a `JSONResponse(status_code=503, content=envelope)` is acceptable since there is no domain-level exception class for "health probe failed" (mirrors BFF `health.py` line 184).
- **Do not register `/metrics`, do not import an OTEL exporter, do not call `setup_otel(...)`.** Per the sprint-change cut + AR1 note. Archetype boilerplate stays inert.
- **Do not edit `tools/fastapi-archetype/`.** Patching the cloned archetype in place is invisible to anyone re-cloning. If the archetype has a bug (Story 1.3 hit `--no-demo`), pin to a known-good SHA and patch the scaffolded output.
- **Do not invent new `ErrorCode` values that aren't immediately consumed.** Story 1.3 proved this discipline; carry it forward. The architecture enumerates the final set; each value lands when its first consumer arrives.
- **Do not add a `ports:` block to the RS service.** The RS is internal-only. The only port published to the host is the BFF's 8000 (browser-facing OIDC redirect).
- **Do not modify the BFF service block** in `compose/app.yml` (AC #10 / #14). The BFF's `depends_on` does not gain `resource-server`. When the RS is down, the BFF surfaces 503 honestly via Story 3.5's `ResourceServerClient` — that honest failure surface is the whole point of FR-ERROR-01 / J6.
- **Do not add `e2e` to the RS service's `profiles:` list yet.** That happens in Story 3.6 paired with the `compose/app.e2e.yml`-style overlay for `ENABLE_TEST_RESET=true` and the `killRs`/`startRs`/`resetState` helper extensions.
- **Do not couple the RS to BFF env vars.** The RS does not read `BFF_*` at all. If the archetype emits a `BFF_*` field in its template, remove it from the RS's `.env.example` and `core/config.py`.
- **Do not bake the SPA into the RS image.** Only the BFF serves the SPA (per AR24 / Story 1.14). The RS Dockerfile is Python-only, single-language, no Node stage.
- **Do not modify Story 1.2 / 1.3 / 1.14 artifacts** (keycloak/*, services/bff/**, the BFF block in compose/app.yml, the root .env.example except where AR29 already covers RS vars). Those are merged and stable.

### Naming and pattern compliance (architecture §"Implementation Patterns & Consistency Rules")

Mandatory references (lines 538–820):

- **Python files:** `snake_case.py`; tests `test_<name>.py`. Service package name: **`resource_server` (underscore)** — the directory `services/resource-server/` is kebab-case (operational name), but the importable Python package is `resource_server` (PEP 8 + matches architecture lines 964–995).
- **Classes:** `PascalCase`. **Enums:** members `UPPER_SNAKE_CASE`.
- **HTTP API paths:** `kebab-case`. `/health` is non-versioned (mechanics). `/v1/*` for domain APIs — none in scope for this story.
- **JSON field names:** `snake_case` in both directions.
- **Headers:** `X-Request-Id` set by a simple UUID middleware in the request pipeline (per architecture line 562 post-sprint-change). The archetype may emit this; if so, it carries over for free.
- **Tests mirror source paths.** A handler in `src/resource_server/api/health.py` is tested by `tests/api/test_health.py`.

### Testing approach for `/health`

Per architecture §"Testing patterns" + AR33: pytest async, in-memory SQLite + `TestClient`, archetype's synthetic-IdP pattern for auth tests (the latter lands in Story 3.2; not needed here).

**`tests/api/test_health.py` cases (minimum 11):** see Task 4's bullet list. Mock the JWKS HTTP call via `httpx.MockTransport` (same pattern as BFF Story 1.3 line 309). Mock DB / Alembic state by monkeypatching the helpers (or using a fresh in-memory SQLite that is deliberately not at head). Do **not** spin up a real Keycloak in unit tests.

### Practical notes & gotchas

- **`uv sync --frozen`** requires `uv.lock` present and consistent with `pyproject.toml`. The archetype emits both; do not run `uv lock` (which would regenerate the lockfile and shift versions). Same warning as Story 1.3.
- **Python 3.14** is the archetype's pinned version. `uv` will fetch the right toolchain if local Python isn't 3.14.
- **`docker compose config`** does not start containers. Runtime start-up is gated by Keycloak (Story 1.2) and is therefore out of scope for AC verification (mirrors Story 1.3 AC #10 + 1.3 review's decision-needed #2 — bootstrap pre-step required).
- **`rs_data` named volume**: declare it at the bottom of `compose/app.yml` alongside `bff_data`:
  ```yaml
  volumes:
    bff_data: {}  # existing (Story 1.3)
    rs_data: {}   # NEW (this story)
  ```
  Compose creates each on first `docker compose up`; both persist across `down` and are destroyed by `down -v`.
- **Service name `resource-server` (hyphen) vs package `resource_server` (underscore).** Docker container names use hyphens; Python imports use underscores. The Dockerfile's entrypoint uses the Python module path (`resource_server.main:app`), and compose's `container_name` and DNS-resolvable hostname use the hyphenated name (`resource-server`). This split is normal and matches the architecture line 964 spelling.
- **The BFF reaches the RS at `http://resource-server:8000`** via Docker DNS. Story 3.5 will hard-code this base URL on the BFF's `ResourceServerClient` (via an env var like `RS_BASE_URL`, or by reading `OIDC_AUDIENCE` and mapping — implementer's choice in Story 3.5). This story does NOT add such an env var; the RS doesn't know its own consumers.
- **No published port.** `curl http://localhost:8000/health` from the host will hit the BFF (Story 1.3 published `8000:8000`). To reach the RS from the host for ad-hoc testing, use `docker exec resource-server …` or temporarily add `ports: ["8001:8000"]` to the RS block locally (do NOT commit that — it violates AC #9).

### Previous story intelligence

**Story 1.3 (BFF scaffold) — direct analog.** Read this carefully when implementing:

- **`build_template.py -o` flag is the parent dir, not the destination.** Story 1.3 first ran `-o services/bff` and cookiecutter rejected it (existing non-empty dir). The correct invocation is `-o services` with `-n bff` → output at `services/bff`. Apply the same fix here: `-o services -n resource-server` → output at `services/resource-server`. (Story 1.3 dev log lines 430–432.)
- **`--no-demo` leaves dangling imports.** Upstream defect in `remove_demo.py` — the cleanup misses `dummy` references in `main.py`, `models/entities/__init__.py`, `models/dto/v1/__init__.py`, `factories/__init__.py`. Fix in the scaffolded output, NOT in `tools/fastapi-archetype/`. (Story 1.3 dev log lines 440–443.)
- **Initial coverage may be ~83%, not >90%, because of `auth/entra.py`.** The archetype's Azure-AD bearer module is dead code for both BFF and RS (BFF uses cookie-session OIDC; RS will use `oidc_bearer` in Story 3.2). Add it to `[tool.coverage.run].omit` with a documenting comment. Re-run pytest --cov → 96.15%+ (Story 1.3 result). (Story 1.3 dev log lines 455–462.)
- **Alembic wiring pattern.** Story 1.3 added `uv add alembic && uv run alembic init -t async alembic` and rewrote `alembic/env.py` to read settings via the BFF's `effective_database_url`. Mirror that on the RS: rewrite `alembic/env.py` to read `RS_DATABASE_URL` (via the archetype's `cfg.effective_database_url` or analogous). The `_to_async_url` import is private — Story 1.3 deferred that via D19; don't fix it here (cross-service consistency).
- **The pyproject.toml `alembic.ini` `sqlalchemy.url` line** is commented out in Story 1.3; resolved at runtime by `env.py`. Do the same on the RS.
- **D4 `.dockerignore` strategy** flipped from per-service (Story 1.3) to root-context (Story 1.14). For the RS, go directly to the post-1.14 posture — root context, root `.dockerignore` does the work. The per-service file emitted by the archetype is left in place for documentation parity but not consulted.
- **Required-fail-fast for secrets/IDs.** Story 1.3 review's decision-needed #3 added a `model_validator` rejecting empty/whitespace `BFF_CLIENT_SECRET`. Mirror that for the RS's `OIDC_ISSUER_URL` / `OIDC_JWKS_URL` / `OIDC_AUDIENCE` — declare them required, reject whitespace-only values at AppSettings construction. Two tests per field (missing + whitespace-only).
- **Health response sanitization.** Story 1.3 review's patch P4 strips verbose probe-detail strings from the 503 response body (logged server-side instead) so an unauthenticated caller cannot fingerprint internal state. Apply the same pattern from the start here.
- **`docker compose config` bootstrap pre-step.** Story 1.3 review's decision-needed #2 documented `cp .env.example .env` + `cp services/bff/.env.example services/bff/.env`. Add the RS to this list (Task 6) and update README in a later story (5.3) — not this one.

### Git intelligence (recent commits)

```
060df66 feat: minor fixes to the CSFR token naming
ca02146 fix: BFF drops offline_access scope + realm declares profile scope
180b1e2 chore(1.14): code review — F1 path-traversal guard, F2 docstring fix, 5 defers; close epic-1
501a85a Merge story 1.14 — dev-story phase
96d6640 feat(1.14): BFF multi-stage build serves SPA bundle (closes D46, unblocks 5.4)
```

- Epic 1 is closed; epic-1-retrospective is `optional` (skippable).
- Current working branch is `epic-3` (already checked out — verified by `git branch --show-current`).
- `services/resource-server/` is still `.gitkeep`-only — the RS tree is a clean slate ready for `build_template.py`.
- `compose/infra.yml`, `keycloak/realm-bmad-books.json`, `keycloak/Dockerfile`, `services/bff/**` are all landed and stable; **do not modify them** in this story.
- `compose/app.yml` carries the BFF + Playwright blocks and the `bff_data` volume — this story extends it with the RS block + `rs_data` volume.
- The latest commits (`060df66`, `ca02146`) are minor BFF / realm fixes that don't touch the RS surface.

### Latest tech information

- **Python 3.14** is the archetype's pinned version (GA October 2025). Matches BFF.
- **FastAPI / SQLModel / uv** — all pinned by the archetype's `pyproject.toml`; do not override.
- **Ruff / ty / pytest-cov** — pinned by the archetype. Coverage threshold `fail_under = 90`.
- **`pyjwt[crypto]`** — *not yet needed* in Story 3.1. Lands in Story 3.2's `oidc_bearer.py`. Do not add this dependency in this story.
- **`httpx`** — already in the archetype's deps (used by the BFF for OIDC discovery / token exchange; the RS uses it for JWKS reachability in `/health` + by `PyJWKClient` in Story 3.2). No extra add needed.
- **Docker Compose v2.20+** — required for the top-level `include:` (Story 1.1 dependency carried forward). `docker compose config` and `docker compose build` are the verification commands.

### Project Structure Notes

- RS source root is `services/resource-server/src/resource_server/` — the package name is `resource_server` (underscore), per architecture lines 964–995.
- The RS's `pyproject.toml` declares the project name (archetype probably emits `resource-server` or `bmad-books-resource-server`; align with the entrypoint import path `from resource_server.main import app`).
- Tests live in `services/resource-server/tests/` and mirror `src/resource_server/`. Do not create a top-level `tests/` at the repo root.
- The RS's `Dockerfile` lives at `services/resource-server/Dockerfile`; the `entrypoint.sh` lives at `services/resource-server/entrypoint.sh`. The build `context:` in `compose/app.yml` is `..` (repo root), and `dockerfile: services/resource-server/Dockerfile`.
- The named volume `rs_data` is declared in `compose/app.yml`'s top-level `volumes:` block and mounted at `/data` on the RS container (per AR6).
- No top-level aggregator (`pyproject.toml`, `package.json`) at repo root — the monorepo is per-service.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 3.1` lines 1119–1153] — canonical story spec and Given/When/Then ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` AR1 line 46, AR3 line 48, AR6 line 57, AR8 line 59, AR15 line 72, AR17 line 74, AR19 line 76, AR25–AR29 lines 88–92, AR33 line 98] — archetype mandate, RS OIDC bearer plugin, DB engine, RS schema (deferred), path layout, ErrorCode envelope, timeouts, repo structure, compose composition, env vars, backend test patterns.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` A2 line 348] — RS JWT validation library (PyJWT + PyJWKClient); architectural rationale for genericizing the archetype's `entra` mode.
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` C1 lines 360–361, C3 lines 380–388, C5 lines 396–409, C6 lines 411–416] — path layout, RS endpoints (Story 3.3 territory), ErrorCode enum reference, timeouts (AR19).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` I1 lines 462–481, I2 lines 483–487, I3–I5 lines 489–507] — repo layout, compose composition, profiles, env-var enumeration, persistence model (rs_data named volume at /data).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Implementation Patterns & Consistency Rules` lines 538–820] — naming, structure, format, communication, process patterns. Mandatory.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 954–1007] — exact RS service-tree layout this story should produce + the test mirror.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Architectural Boundaries` lines 1092–1141] — RS data boundary (`reading_speeds` keyed by `sub`; BFF never reads), JWKS-only Keycloak read, no cross-service Python imports.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details` lines 1317–1373] — health-check semantics (DB + Alembic + JWKS — line 1327), Alembic-on-startup entrypoint pattern, no `/metrics` / no OTEL exporter posture.
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`] — confirmation that observability stack is removed; no `/metrics`, no OTEL collector.
- [Source: `_bmad-output/implementation-artifacts/1-3-bff-scaffold-from-archetype-baseline-health-lint-test-gates.md`] — **direct analog** for this story. Re-read its Dev Notes (lines 151–402) and Dev Agent Record (lines 404–602) before starting. Decision-needed resolutions (lines 613–618) and patches P1–P11 (lines 619–632) carry over.
- [Source: `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`] — sets the root-build-context posture that this story mirrors for `.dockerignore` and Dockerfile context (AC #12).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D1, D4, D22] — items this story addresses or preempts.
- [Source: `services/bff/Dockerfile`, `services/bff/entrypoint.sh`, `services/bff/src/bff/api/health.py`, `services/bff/.env.example`, `compose/app.yml`] — five reference files; the RS counterparts should look structurally identical modulo the module name (`resource_server` vs `bff`), the env-var subset, and the JWKS-vs-OIDC-discovery probe.
- [Source: `CLAUDE.md` at repo root] — project convention: invoke Python as `python`, never `python3`.
- [Source: `[[project-bmad-books-backend-archetype]]` — user memory] — backend archetype mandate, observability carve-out.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-dev-story workflow)

### Debug Log References

_(populated by the dev agent during implementation)_

### Completion Notes List

_(populated by the dev agent on completion)_

### File List

_(populated by the dev agent on completion)_
