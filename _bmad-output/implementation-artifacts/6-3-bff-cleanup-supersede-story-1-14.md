---
status: done
story_key: 6-3-bff-cleanup-supersede-story-1-14
epic: 6
prerequisites: Story 6.2 (SPA Dockerfile + compose service + Keycloak realm port pin) is `done` and has produced a working `spa` compose service that owns the host-facing port (`:4000` by default) and proxies `/auth/*` `/api/*` `/v1/*` to the BFF on the compose network. After 6.2 close the BFF has already lost its `ports: ["8000:8000"]` mapping, `BFF_BASE_URL` has already flipped to `http://localhost:${SPA_HOST_PORT:-4000}`, and the Keycloak realm registers `:4000` as the OAuth redirect host — meaning Story 1.14's SPA-in-BFF surface is **unreachable from the browser** by the time 6.3 starts, but the static-serve code path is still present in the BFF image. Story 6.3 removes that code path (Dockerfile Node-builder stage; `_SPA_DIR` + `_register_spa` + the conditional mount in `main.py`; `tests/api/test_static.py`) and reverts the BFF's compose `build.context` from the repo root back to `../services/bff` (since the Node stage no longer needs to reach `spa/`). Source-of-truth for Epic 6 scope is `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.3 + §2.4 Story 1.14 supersession + §2.5 Compose / Docker / Keycloak impact; Epic 6 is NOT yet in `_bmad-output/planning-artifacts/epics.md` (Story 6.4 owns that edit).
supersedes: Story 1.14 (full — this story removes the Dockerfile Node-builder stage, the `services/bff/src/bff/main.py` static-mount machinery, and the `services/bff/tests/api/test_static.py` test surface that Story 1.14 introduced. The 1.14 story file stays in the repo as the codified history of the SPA-in-BFF posture; a `supersession` note is appended to its frontmatter pointing here.)
created: 2026-05-19
baseline_commit: ed34ac7
---

# Story 6.3: BFF cleanup — supersede Story 1.14

Status: done

<!-- Sprint: Epic 6 (Frontend Split & SSR Edge). Third story in Epic 6. -->
<!-- Follows: Story 6.2 (SPA Dockerfile + compose service + Keycloak realm port). -->
<!-- Precedes: Story 6.4 (re-validation — e2e + smoke + docs sweep). -->
<!-- Source of truth: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.3 + §2.4 Story 1.14 supersession. -->

## Story

As the BFF codebase,
I want to delete every SPA-serving surface Story 1.14 introduced — the Node-builder Dockerfile stage, the `StaticFiles` / `FileResponse` machinery in `main.py`, the static-serving test suite, and the repo-root build context the Node stage required — and to restore the BFF's per-service build context,
so that the BFF becomes purely API-only as Epic 6's split intended, the dead static-serve attack surface and Node toolchain are removed from the image, `git grep` confirms zero residual references to the SPA-in-BFF model, and Story 6.4 can sweep the e2e / docs surfaces on top of a clean BFF.

## Scope (read this first)

Story 6.3 owns the **BFF cleanup** half of the split. Story 6.1 produced the SSR runtime, Story 6.2 wired the new `spa` compose service and flipped the host port + Keycloak realm; Story 6.3 deletes everything Story 1.14 added to the BFF and reverts the BFF's build context. The BFF's API surface (`/api/me`, `/auth/*`, `/v1/*`, `/health`) is **byte-identical** before and after this story — nothing in the request/response shape, the middleware stack, the router order, or the OAuth handshake changes. Only the SPA-serving augmentation comes out.

**Deliverables:**

1. **`services/bff/Dockerfile`** (MODIFIED) — Delete Stage 0 (`FROM node:22-slim AS node-builder` + its WORKDIR + the two COPY lines + `RUN npm ci` + `RUN npm run build`) entirely. Delete the `COPY --from=node-builder /spa/dist/spa/browser /app/static` line in Stage 2 plus its two preceding comment lines. Update the build-context comment block in Stage 1 to reflect the per-service revert. After this, the file has two stages (Python `builder` + final runtime) and no Node toolchain anywhere.
2. **`services/bff/src/bff/main.py`** (MODIFIED) — Delete:
   - `from pathlib import Path` (line 3) — no other consumer.
   - `Request` from the `fastapi` import (line 5) — no other consumer.
   - `JSONResponse` import (line 8) — no other consumer (`bff.core.errors` owns the error-envelope rendering; main.py doesn't construct JSON responses anywhere else).
   - `FileResponse, Response` import from `starlette.responses` (line 9) — only used in `_register_spa`.
   - `StaticFiles` import from `starlette.staticfiles` (line 10) — only used in `_register_spa`.
   - The `_SPA_DIR` constant + its leading comment block (lines 28–31).
   - The entire `_register_spa(application, static_dir)` function (lines 34–93) — including the path-traversal guard and the 404 envelope branch (the envelope contract continues to live in `bff.core.errors`; main.py no longer registers a catch-all that emits it, which is correct now that no request can reach `bff:8000/<unknown>` from the browser).
   - The conditional mount block at the end of the file (lines 144–149) — `if _SPA_DIR.is_dir(): _register_spa(app, _SPA_DIR)` plus its leading comment.
3. **`services/bff/tests/api/test_static.py`** (DELETED) — the four pytest cases (AC7a/b/c from Story 1.14 + the path-traversal probe added during 1.14 review) all depend on `_register_spa` and the static-dir fixture; without the function they're dead code. Delete the file outright; no replacement.
4. **`compose/app.yml`** (MODIFIED) — `bff:` service `build:` block:
   - Change `context: ..` (repo root) → `context: ../services/bff` (per-service, restoring the pre-1.14 form).
   - Delete the `dockerfile: services/bff/Dockerfile` line — with a per-service context, the default `./Dockerfile` resolution works again.
   - Update the comment block above the `build:` (currently lines 30–35, citing "Story 1.14 (closes D4): build context is the repo root so the Node builder stage can COPY spa/...") to cite Story 6.3 reverting it: "Story 6.3: per-service context restored — the Node builder stage was removed and the BFF no longer needs to reach `spa/`. The repo-root `.dockerignore` is no longer consulted for this build; `services/bff/.dockerignore` becomes load-bearing again."
   - Also update the file-header comment block (currently lines 1–26) to drop the Story 1.14 SPA-in-BFF claim: line 5–7 currently reads "Story 1.14 (AR24): the SPA bundle is compiled inside the BFF image via a multi-stage Dockerfile (Node build stage → Python runtime stage); there is no separate `spa` service." Replace with a Story 6.3 line citing the post-split state: "Story 6.2 (Epic 6): the SPA is a first-class compose service (`spa:` below) that owns the host-facing port `:${SPA_HOST_PORT:-4000}` and reverse-proxies `/auth/*` `/api/*` `/v1/*` to the BFF over compose DNS. Story 6.3 reverted the BFF's static-serve code path and per-service build context — the BFF is now API-only." Keep the D140/D141 paragraph (lines 9–14) and the Story 1.12 paragraph (lines 19–26) untouched.
5. **`docker-compose.yml`** (MODIFIED) — the top-level file's header comment block (currently lines 1–14): line 6 currently advertises "+ SPA bundle baked into the BFF image (Story 1.14)" on the `compose/app.yml :` line. Story 6.2 was tasked with refreshing this to "BFF, Resource Server, SPA SSR edge (Stories 1.3, 3.1, 6.2). The BFF's Story-1.14 static-serve code path is still in the BFF image but unreachable from the browser; Story 6.3 removes it." Story 6.3 must now refresh again to the post-cleanup state: drop the trailing "still in the BFF image but unreachable...; Story 6.3 removes it" sentence, leaving the line at "BFF (API-only), Resource Server, SPA SSR edge (Stories 1.3, 3.1, 6.2)." Also update the "dev workflow" paragraph (lines 8–14): currently it mentions "`cd spa && npm start` on the host" — Story 6.2 was tasked with retiring that phrasing; 6.3 verifies that the post-6.2 wording is accurate and tightens it if needed (the dev workflow is now bare `docker compose up`; the SPA SSR edge is a compose service).
6. **`_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`** (MODIFIED) — append a supersession note to the frontmatter. Add three lines after the existing `created: 2026-05-15` line (line 4):
   ```yaml
   superseded_by: 6-3-bff-cleanup-supersede-story-1-14
   superseded_on: 2026-05-19
   supersession_rationale: Epic 6 split the SPA out of the BFF image into its own Angular SSR Node container (Sprint Change Proposal 2026-05-19). Story 6.3 removed the Node-builder Dockerfile stage, the StaticFiles + FileResponse machinery in main.py, the test_static.py test surface, and reverted the BFF's compose build context to per-service. This story file remains in the repo as the codified history of the pre-Epic-6 SPA-in-BFF posture; its acceptance criteria are no longer load-bearing.
   ```
   Do NOT edit the body, the ACs, the tasks, the Dev Notes, the Dev Agent Record, or any other part of the 1.14 story file — only the frontmatter gets the supersession metadata. The historical artefact stays verbatim.
7. **`_bmad-output/implementation-artifacts/sprint-status.yaml`** (MODIFIED) — flip `6-3-bff-cleanup-supersede-story-1-14: backlog` → `ready-for-dev` (this story-create commit) → `in-progress` (dev start) → `review` (close). Update `last_updated` per the existing convention.

What this story **does NOT do** (handled by other Epic 6 stories or out of Epic 6's scope — do not touch any of these here):

- **`services/bff/.dockerignore`** — already exists and excludes `tests/`, `docs/`, `htmlcov/`, etc. After this story it becomes load-bearing again (per-service context resumes consulting it instead of the repo root's). Verify against AC1's `docker build services/bff` probe — if a file leaks into the context that shouldn't, surface in Anomalies. Do NOT proactively churn this file in 6.3 unless verification reveals a real gap.
- **`.dockerignore`** (repo root) — Story 1.14 added five `services/bff/...` exclusion entries (lines 23–27) specifically because the root context applied. After 6.3 the root context is no longer used for the BFF build, so those five lines become belt-and-suspenders / informational. **Leave them in place** — the Resource Server still uses a root build context (`services/resource-server/Dockerfile` per `compose/app.yml:108–114`), so the file remains live and the BFF entries don't actively hurt. Removing them would be a stylistic-only churn that triggers a multi-service review surface for no functional gain. The BFF-specific entries (`services/bff/tests/`, `services/bff/docs/`, `services/bff/.ruff_cache/`, `services/bff/.githooks/`) can be considered no-ops for the BFF post-6.3 — they will continue to filter the Resource Server's build context coincidentally (none of those paths exist there) but cause no harm.
- **`services/resource-server/**`** — zero Epic 6 changes touch the RS. Its build context stays at `..` (repo root); its Dockerfile is unchanged.
- **`spa/**`** — Stories 6.1 (SSR runtime) and 6.2 (Dockerfile + compose service) own everything under `spa/`. Story 6.3 must not touch a single file there.
- **`compose/infra.yml`** — Story 6.2 added the `SPA_HOST_PORT` env pass-through on Keycloak. Story 6.3 does not edit this file.
- **`compose/app.e2e.yml`** — Story 6.4 sweeps the e2e overlay. 6.3 must not touch it. The overlay only adds `environment:` entries to the BFF and RS services; it carries no `build:` block, so the BFF context change in 6.3 propagates correctly without an overlay edit.
- **`keycloak/realm-bmad-books.json`** — Story 6.2 owns the redirect URI / webOrigins / post.logout.redirect.uris substitutions. Story 6.3 does not touch the realm JSON.
- **`e2e/playwright.config.ts`, `e2e/**`** — Story 6.4 sweeps the e2e config. 6.3 does not touch it. After 6.3 close, `just e2e-up` continues to fail (same state as after 6.2) because the e2e overlay still points at `:8000` and the realm has flipped to `:4000`; this is expected and explicitly handed off to 6.4.
- **`_bmad-output/planning-artifacts/architecture.md`, `PRD.md`, `epics.md`** — Story 6.4 owns the F3 / I6 / A8 edits, the F7 / I9 inserts, the §6 PRD clarification, and the Epic-6 epics.md block. Story 6.3 does not amend any planning artefact other than appending the supersession metadata to the 1.14 implementation artefact (which is an implementation artefact, not a planning artefact — see Deliverable 6).
- **`README.md`, `docs/smoke-run.md`, `docs/security-review.md`, `docs/coverage-report.md`** — Story 6.4 owns all docs.
- **`Justfile`** — no recipe changes. `just config` continues to validate the baseline stack; `just e2e-up` continues to fail until Story 6.4 sweeps the e2e config. Story 6.3 must not add a `just bff-only` recipe or any other helper.
- **`services/bff/src/bff/middleware/security_headers.py`** — keep. The CSP middleware moves to the SPA edge in Story 6.4 (per Sprint Change Proposal §2.3 A8 amendment). Story 6.3 leaves CSP attachment on the BFF; HTML responses no longer come out of the BFF post-6.3, so the request-`Accept`-driven attachment predicate (`_attach_csp`) simply never fires from outside the compose network. Internal compose-DNS callers (the SPA edge's proxy) get the same CSP-less JSON responses as before. D369 in deferred-work.md notes the predicate would ideally be response-`Content-Type`-driven once SSR moves the CSP source — that's Story 6.4's pickup, not 6.3's.
- **`services/bff/src/bff/auth/csrf.py`** — keep. The CSRF middleware compares the request `Origin` header against `settings.bff_base_url`. Story 6.2 already flipped that to `http://localhost:${SPA_HOST_PORT:-4000}`, and `http-proxy-middleware` v3 forwards the browser's `Origin` header unchanged to the BFF (Story 6.2 AC6 failure-prevention note 2 documents this). 6.3 does not touch the CSRF surface.

Why this strict scope split: the BFF cleanup is a deletion-heavy change with a small but precise edge — getting the `compose/app.yml` build-context revert wrong (or leaving a stale `dockerfile:` key) makes the BFF image fail to build. Keeping the diff to deletions + the four-line compose surgery makes the review surface trivial to verify. Folding 6.4's doc sweep or 6.4's e2e config revert into 6.3 buries the BFF deletions under noise.

## Acceptance Criteria

> Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.3 (AC1–AC5 there). Re-derived here with concrete file paths, exact symbols verified against the current `services/bff/src/bff/main.py` / `services/bff/Dockerfile` / `compose/app.yml` at HEAD `ed34ac7`, and probe commands adapted from Story 6.2's verification pattern.

### AC1 — BFF Dockerfile has no Node toolchain; `docker build services/bff` succeeds standalone

**Given** the SPA is now built and served by the `spa` compose service (Stories 6.1 + 6.2),
**When** the developer runs `docker build -t bff-cleanup-test services/bff/` from the repo root (note: per-service build context, no `-f` flag needed because the Dockerfile is at `services/bff/Dockerfile`),
**Then** the build succeeds and produces an image that:

- Has **no `node-builder` stage** — `docker history bff-cleanup-test --no-trunc` shows no `node:22-slim` base, no `npm ci`, no `npm run build`, no `COPY spa/...` lines.
- Has **two stages only**: Stage 1 `builder` (`python:3.14-slim` with `uv sync`) and Stage 2 final runtime (`python:3.14-slim` with the BFF venv).
- Has **no `COPY --from=node-builder` line** anywhere — `grep -nE 'node|spa|static' services/bff/Dockerfile` returns zero matches against the post-edit file (the only legitimate residual would be a `WORKDIR /app` line which contains the substring `app` but not any of the three patterns).
- Has **no `/app/static` directory** in the runtime layer — `docker run --rm --entrypoint sh bff-cleanup-test -c "ls /app"` shows `.venv`, `alembic.ini`, `alembic/`, `entrypoint.sh` and NOTHING else under `/app/` (no `static/`).
- Runs the FastAPI app standalone — `docker run --rm -e BFF_DATABASE_URL=sqlite+aiosqlite:///:memory: -p 18000:8000 bff-cleanup-test` followed by `curl -sS http://localhost:18000/health` returns `{"status":"ok"}` (or the BFF's health envelope shape per `services/bff/src/bff/api/health.py`).
- Image size shrinks meaningfully — the post-1.14 image was ~600–700 MB (Python slim + Node slim layers + SPA bundle); the post-6.3 image should be ~250–350 MB (Python slim only). Record the empirical `docker images bff-cleanup-test` size in Completion Notes; if it's >450 MB something larger than the BFF venv got copied in, audit the Stage 2 COPY lines.

**And** the per-service build context works correctly — `docker build services/bff/` (note: NO `-f services/bff/Dockerfile` needed when the Dockerfile is in the context root) succeeds with the same image. The Stage 1 `RUN --mount=type=bind` paths in the Dockerfile must resolve relative to the per-service context post-edit (see AC6 for the COPY-path implications); if they still reference `services/bff/uv.lock` etc. the build fails. AC6 calls out the COPY-path revert; AC1 verifies the integrated behavior.

> **Verification commands** (Task 8 will execute):
> - `docker build -t bff-cleanup-test services/bff/` → exits 0.
> - `docker history bff-cleanup-test --format '{{.CreatedBy}}' | grep -E 'node|npm' | wc -l` → `0`.
> - `docker run --rm --entrypoint ls bff-cleanup-test /app | tr ' ' '\n' | sort` → `.venv`, `alembic`, `alembic.ini`, `entrypoint.sh` (no `static`).
> - `docker images bff-cleanup-test --format '{{.Size}}'` → record in Completion Notes.
>
> **Failure-prevention note (uv bind mounts):** The Stage 1 `RUN --mount=type=bind,source=services/bff/uv.lock,...` lines (current `services/bff/Dockerfile:29–31`) reference `services/bff/...` paths because the build context was the repo root. After 6.3's revert to per-service context, those bind-mount sources must change to bare `source=uv.lock` (and `pyproject.toml`, `.python-version`). The Stage 1 `COPY services/bff/ /app/` (line 34) must similarly revert to `COPY . /app/`. These are mechanical reverts of Story 1.14's AC2 changes; the pre-1.14 Dockerfile shape is the post-6.3 target. Verify with `git log -p --follow services/bff/Dockerfile` if the pre-1.14 shape needs to be referenced.

### AC2 — `GET http://bff:8000/` from inside the compose network returns the 404 envelope (no static fallback)

**Given** the full compose stack is up (`docker compose up -d --wait` with the post-6.2 / post-6.3 topology — Keycloak + BFF + RS + SPA),
**When** the developer runs `docker compose exec spa node -e "fetch('http://bff:8000/').then(r => r.text()).then(t => console.log(r.status, t))"` (or equivalent; the SPA container has Node 22 with `fetch` global per Story 6.2 AC8),
**Then** the response is HTTP 404 with body byte-for-byte equal to FastAPI's default empty-router 404 (NOT the project's `not_found` envelope — see failure-prevention note 1 below).

> **Critical clarification:** Story 1.14's `_spa_or_404` catch-all returned the **project's `{"errorCode":"not_found","message":"Not found","detail":null}` envelope** for non-HTML clients hitting unknown paths (closing D16 for GET requests). After 6.3 removes the catch-all, FastAPI's built-in `Not Found` handler responds at unknown paths with its default `{"detail":"Not Found"}` shape, NOT the project envelope. **This is a deliberate, intended regression of D16's partial closure**: post-6.3, the BFF is internal-only on the compose network, so the only callers hitting unknown paths are mis-configured proxies or the SPA edge with a routing bug — neither needs the project envelope. The SPA edge surfaces its own 404s to the browser for unknown SPA routes (rendered by Angular Router); the BFF's 404 shape only matters for in-compose-network probes, which can read the FastAPI default fine. **Log this in the supersession note**: D16's partial-closure mechanism (the FastAPI `_spa_or_404` catch-all) is removed; reopen D16 as a follow-up if a future use case needs the BFF to emit the project envelope on unknown paths.

> **Failure-prevention note 1:** Do NOT add a replacement catch-all in `main.py` to preserve the envelope shape. The exception-handler infrastructure (`AppException`, `RequestValidationError`) already covers application-defined error paths; the unknown-path 404 is a different surface and the project envelope was never load-bearing for it (D16 was deferred-then-partially-closed-by-1.14, not "production-required"). Adding a catch-all back would re-introduce ordering coupling with future route registrations (the catch-all must be LAST) for no functional gain.
>
> **Failure-prevention note 2:** Do NOT confuse `GET http://bff:8000/` (root, what AC2 probes) with `GET http://bff:8000/health` (the live healthcheck route). The health endpoint stays registered and returns 200 with the BFF's health envelope. `GET http://bff:8000/` is the unknown-path probe; it returns 404. Both behaviors must hold at AC2 close.
>
> **Failure-prevention note 3:** From the **host**, `curl http://localhost:8000/` is still `Connection refused` (Story 6.2 AC5 removed the BFF's host-port publish). AC2 probes from **inside the compose network** via `docker compose exec`, where `http://bff:8000` is resolvable via compose DNS. If `docker compose exec spa node ...` returns `connection refused`, check that the SPA container is healthy and on the default compose network alongside the BFF.

### AC3 — BFF API surface byte-identical to pre-6.3

**Given** the post-6.3 BFF image is up in compose,
**When** the developer hits each documented BFF endpoint from inside the compose network or from the host through the SPA proxy at `:4000`,
**Then** every response is byte-identical to the pre-6.3 response:

- `GET http://bff:8000/health` (from inside compose) — 200, BFF health envelope unchanged.
- `GET http://localhost:4000/api/me` (through SPA proxy, anonymous) — 401 with `{"errorCode":"session_expired","message":"Session expired or not present","detail":null}` (byte-identical to Story 6.2 AC4).
- `GET http://localhost:4000/auth/login` (through SPA proxy, fresh state) — 302 with `Location:` containing the Keycloak authorize URL, `redirect_uri` query param decodes to `http://localhost:4000/auth/callback` (byte-identical to Story 6.2 AC6 step 2).
- `GET http://localhost:4000/v1/books` (through SPA proxy, anonymous) — 401 with the same session-expired envelope shape as `/api/me`.
- OAuth happy path against `testuser/testpassword` completes end-to-end through `http://localhost:4000` (re-runs Story 6.2 AC6 verbatim). Login, redirect to Keycloak, login, callback, `/books` rendered with TopChrome logged-in state, logout, back to `/login`.

The point of AC3 is to prove that the cleanup does NOT regress any API behavior. The BFF's middleware stack (CORS, SecurityHeaders, CSRF), routers (health, me, auth, v1, test_reset), exception handlers (AppException, RequestValidationError), and database connection lifecycle are all untouched.

> **Failure-prevention note 1 (middleware import side-effects):** When deleting `from starlette.staticfiles import StaticFiles` etc. from `main.py`, double-check that no transitive import resolution silently breaks (e.g., a downstream module that imports `bff.main` and expects `_register_spa` or `_SPA_DIR` to be exported). The blame list: `services/bff/tests/api/test_static.py` (deleted in this story); `services/bff/tests/conftest.py` (verify no `_register_spa` import); any docs that quote module-level symbols (`docs/security-review.md` was last audited at 5.2 close — check for `_register_spa` / `_SPA_DIR` mentions).
>
> **Failure-prevention note 2 (database connection lifecycle):** The `lifespan` async context manager calls `configure_logging(settings)` on startup and `await dispose_engine()` on shutdown. Both come from imports above the deleted region — they must NOT be touched. Verify by reading `main.py` end-to-end after the edits; the `lifespan` function definition (current lines 96–102) should appear unchanged.
>
> **Failure-prevention note 3 (router order):** The five `app.include_router(...)` calls (health, me, auth, v1, test_reset_router) must keep their current order. Story 1.14 placed the static mount AFTER the routers because Starlette matches in declaration order; removing the mount doesn't change the router order requirement. Verify the post-edit `main.py` still registers routers in the order: `health_router`, `me_router`, `auth_router`, `v1_router`, then `register_test_reset_router(app, settings)`.

### AC4 — `services/bff/tests` exits 0 with the static tests removed, all other tests untouched

**Given** the static-test surface (`services/bff/tests/api/test_static.py`) is deleted,
**When** the developer runs `cd services/bff && uv run pytest` (or `just test` from `services/bff/` if a recipe exists),
**Then** the suite exits 0 with:

- **Zero `test_static.py` tests in the run summary** — `pytest --collect-only services/bff/tests/api/test_static.py` returns `ERROR: not found` (the file is gone). Equivalently, `uv run pytest -k 'test_static'` runs zero tests.
- **All other tests pass** — the pre-6.3 count was 347 (per Story 1.14 Task 4.5 record). The post-6.3 count drops by exactly 4 (the three AC7-mandated tests in `test_static.py` plus the path-traversal probe added during 1.14 review) to **343 tests**, all green. Record the empirical count in Completion Notes.
- **No new test failures** — coverage thresholds, ruff, ty all stay green. Per `services/bff/pyproject.toml` the per-file coverage floor (Story 5.1) was set at 80%; removing `_register_spa` removes the lines that were 100% covered by `test_static.py`, so the file-level coverage for `main.py` may shift slightly. Verify with `uv run pytest --cov=bff --cov-report=term-missing` that `bff/main.py` retains ≥80% line coverage post-edit (the deleted function had ~30 lines of coverage; the remaining ~50 lines of main.py are exercised by health / me / auth / v1 / test_reset tests).

**And** the pre-existing imports in `services/bff/tests/conftest.py` and any shared fixtures must NOT reference `_register_spa` or `_SPA_DIR`. Verify with `git grep -nE '_register_spa|_SPA_DIR' services/bff/tests/` — zero matches.

> **Failure-prevention note 1 (orphan import):** If `tests/conftest.py` happens to import `_register_spa` (it doesn't at HEAD `ed34ac7`, but worth re-verifying as the dev edit lands), the suite errors at collection time. Fix in conftest, do not re-introduce `_register_spa` in main.py.
>
> **Failure-prevention note 2 (coverage configuration):** `services/bff/pyproject.toml` may have a `[tool.coverage.run] omit = [...]` block. If `bff/main.py` is in the omit list (it shouldn't be) the coverage check on this file is degenerate. Verify the file is being measured before claiming the threshold holds.

### AC5 — `git grep` confirms zero residual SPA-in-BFF references in `services/bff/`

**Given** the cleanup is complete,
**When** the developer runs from the repo root:

```bash
git grep -nE 'StaticFiles|_SPA_DIR|_register_spa|_spa_or_404|_json_404|_spa_fallback|FileResponse|/app/static|node-builder|node:22-slim' services/bff/
```

**Then** the output is **empty** — zero matches across the whole BFF tree.

This is the same probe the Sprint Change Proposal §6 success criteria (line 293) calls out. It catches:

- Leftover Python imports (`StaticFiles`, `FileResponse`) in `main.py`.
- Leftover module-level constants (`_SPA_DIR`) and helper names (`_register_spa`, `_spa_or_404`, `_json_404_fallback`, `_spa_fallback`) — the last three names were variants discussed during Story 1.14 implementation; verify none survived as comments or docstring references.
- Dockerfile leftovers (`node-builder` stage name, `node:22-slim` base image, `/app/static` runtime path).

**Run a wider safety-net probe** to catch comment-only leftovers that the narrow probe might miss:

```bash
git grep -nE 'SPA|spa|static' services/bff/ | grep -v 'tests/__pycache__' | grep -v 'htmlcov/'
```

Expected results: this wider probe **may surface a small number of legitimate residual mentions** — e.g., the entrypoint script's comment about uvicorn (`"workers"`), or a docstring that mentions "SPA" in a historical context. Read each match and decide per-line: is the mention still factually accurate post-6.3? If a `main.py` docstring still says "Story 1.14 mounts the SPA bundle", edit it; if `services/bff/README.md` (if present) still describes the multi-stage Node build, edit it. Aim for **zero factually-stale mentions** of SPA-serving behavior in any BFF file. Record the empirical match count and any edits in Completion Notes.

> **Failure-prevention note 1:** The probe runs `git grep`, not plain `grep`, so it respects `.gitignore`. Files in `htmlcov/`, `__pycache__/`, `.venv/` are excluded automatically. If the post-edit `services/bff/` tree has any of those tracked anyway (e.g., a committed coverage report), narrow the probe with `-- 'src/**' 'tests/**' 'alembic/**' 'Dockerfile' '*.py' '*.md' '*.toml' '*.cfg' '*.ini'` to focus on source files.
>
> **Failure-prevention note 2:** The probe is intentionally **case-sensitive**. `SPA`, `Spa`, and `spa` would all be flagged by the wider safety-net probe; the narrow probe targets specific symbols (capitalized class names like `StaticFiles`, private `_SPA_DIR`). Don't suppress matches based on case — read each one.

### AC6 — `compose/app.yml` BFF build context reverted to per-service

**Given** the BFF no longer needs to reach `spa/` from its build context,
**When** the developer inspects `compose/app.yml` `bff:` service `build:` block post-edit,
**Then** it reads:

```yaml
bff:
  build:
    # Story 6.3: per-service context restored — the Node builder stage was
    # removed and the BFF no longer needs to reach `spa/`. The repo-root
    # `.dockerignore` is no longer consulted for this build;
    # `services/bff/.dockerignore` becomes load-bearing again.
    context: ../services/bff
  container_name: bff
  ...
```

(The comment text above is a target shape; minor wording variations are fine if they communicate the same three facts: 6.3 reverted, BFF no longer reaches `spa/`, per-service `.dockerignore` is load-bearing.)

**And the `dockerfile: services/bff/Dockerfile` key is DELETED** — with `context: ../services/bff`, compose's default Dockerfile resolution is `${context}/Dockerfile`, which is `../services/bff/Dockerfile`. The explicit `dockerfile:` key is redundant and was only required when the context was the repo root.

**And the file-header comment block** (currently lines 1–26 at HEAD `ed34ac7`) is refreshed:

- Line 5–7 (Story 1.14 SPA-in-BFF claim) must be replaced with a Story 6.2 / 6.3 statement per Deliverable 4 in Scope. Suggested wording: "Story 6.2 (Epic 6): the SPA is a first-class compose service (`spa:` below) that owns the host-facing port `:${SPA_HOST_PORT:-4000}` and reverse-proxies `/auth/*` `/api/*` `/v1/*` to the BFF over compose DNS. Story 6.3 reverted the BFF's static-serve code path and per-service build context — the BFF is now API-only."
- Keep the D140/D141 paragraph (current lines 9–14) and the Story 1.12 paragraph (current lines 19–26) verbatim.

> **Verification commands** (Task 8 will execute):
> - `grep -n 'context:' compose/app.yml` → BFF block shows `context: ../services/bff`; RS block (line ~113) still shows `context: ..` (unchanged).
> - `grep -n 'dockerfile:' compose/app.yml` → only the RS block matches (`dockerfile: services/resource-server/Dockerfile`); the BFF block has no `dockerfile:` key.
> - `grep -n 'Story 1.14' compose/app.yml` → zero matches in the file-header section (the `Story 1.14 (AR24)` sentence is gone). It is OK if a residual mention survives in a deeper comment if it's factually stating "Story 1.14's posture was X; Story 6.3 reverted to Y" — but the canonical surface (file header) must not present 1.14 as current state.
>
> **Failure-prevention note 1 (RS build context is independent):** The Resource Server's `build:` block (current lines 108–114) uses `context: ..` (repo root) per Story 3.1 / D4 closure. This is **independent** of the BFF's choice and is **NOT reverted in 6.3**. The RS's choice was made for `.dockerignore` parity, not because it needs to reach a sibling — it's a stylistic alignment with the BFF's pre-6.3 posture. Story 6.3 leaves the RS alone. If a future hardening pass wants to revert the RS to per-service context too, that's a separate story.
>
> **Failure-prevention note 2 (compose validation):** After the edit, run `docker compose config` (or `just config`) to validate the resulting compose graph. If the BFF service is unparseable, `compose config` exits non-zero with a clear error.

### AC7 — `docker-compose.yml` top-level header comment reflects post-cleanup state

**Given** Story 6.2 refreshed the `docker-compose.yml` header to call out that the SPA is now a separate service and that Story 6.3 will remove the BFF static-serve code path,
**When** Story 6.3 closes,
**Then** the `docker-compose.yml` header lines 1–14 read (target shape; minor wording variations OK):

```
# docker-compose.yml
# Top-level entry point. Composition is split into two included files so each
# tier stays small and reviewable.
#   - compose/infra.yml  : Keycloak                                  (Story 1.2)
#   - compose/app.yml    : BFF (API-only), Resource Server,
#                          SPA SSR edge                              (Stories 1.3, 3.1, 6.2)
#
# Profile model (D140 follow-up): one profile, `e2e`, scopes the Playwright
# runner only. Bare `docker compose up` brings up the full baseline stack
# (Keycloak + BFF + RS + SPA SSR edge). The retired `default` / `dev` profiles
# produced identical containers; post-Epic-6 the "dev" workflow is bare
# `docker compose up` with the SPA SSR edge as a first-class compose service
# (no host-side `ng serve` step). The e2e workflow stays behind `just e2e-up`.
include:
  - compose/infra.yml
  - compose/app.yml
```

The three required changes vs. the post-6.2 header:

1. The trailing sentence on the `compose/app.yml :` line "The BFF's Story-1.14 static-serve code path is still in the BFF image but unreachable from the browser; Story 6.3 removes it." is **dropped** (it would be inaccurate after 6.3 closes — the code path is no longer in the image).
2. The "dev" workflow sentence "the 'dev' workflow is `docker compose up` plus `cd spa && npm start` on the host" is **dropped** (Story 6.2 should have already retired this; 6.3 verifies and tightens). Replace with "post-Epic-6 the 'dev' workflow is bare `docker compose up` with the SPA SSR edge as a first-class compose service".
3. The `(Stories 1.3, 3.1)` annotation gets `6.2` appended (Story 6.2's Task 8 may have done this already; 6.3 verifies it's present and adds it if missing).

> **Failure-prevention note 1 (compose validation, again):** After this edit, `docker compose config` exits 0 (the change is in comments only; YAML is unaffected). Run it anyway to catch accidental indentation breaks.
>
> **Failure-prevention note 2 (overlap with 6.2):** If Story 6.2's Task 8 left the header in a different shape than this AC targets — that's fine, 6.3 is the canonical close. Read the post-6.2 state and edit to the post-6.3 target above, regardless of intermediate Story 6.2 wording.

### AC8 — Story 1.14 frontmatter carries the supersession metadata

**Given** Story 1.14 is the codified pre-Epic-6 SPA-in-BFF posture,
**When** Story 6.3 closes,
**Then** `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` frontmatter (currently lines 1–5) carries three new lines after the existing `created: 2026-05-15`:

```yaml
---
status: done
story_key: 1-14-bff-multi-stage-build-serves-spa-bundle
created: 2026-05-15
superseded_by: 6-3-bff-cleanup-supersede-story-1-14
superseded_on: 2026-05-19
supersession_rationale: Epic 6 split the SPA out of the BFF image into its own Angular SSR Node container (Sprint Change Proposal 2026-05-19). Story 6.3 removed the Node-builder Dockerfile stage, the StaticFiles + FileResponse machinery in main.py, the test_static.py test surface, and reverted the BFF's compose build context to per-service. This story file remains in the repo as the codified history of the pre-Epic-6 SPA-in-BFF posture; its acceptance criteria are no longer load-bearing.
---
```

The `status: done` field stays — 1.14 was completed at its time; supersession is a separate concept from completion. The story file body (Story / Acceptance Criteria / Tasks / Dev Notes / Dev Agent Record sections) is NOT edited — those sections are the historical record. Only the frontmatter gets the supersession metadata.

> **Failure-prevention note 1 (YAML syntax):** The `supersession_rationale` field is a long string. Use a YAML literal block scalar (`>` or `|`) only if the rationale spans multiple lines; for a single-line rationale (as suggested above), the inline string form is correct. Verify with `python -c "import yaml; print(yaml.safe_load(open('_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md').read().split('---')[1]))"` that the frontmatter parses.
>
> **Failure-prevention note 2 (don't edit the body):** Tempting to add a "SUPERSEDED" banner at the top of the Story section. Do not. The 1.14 file's body is the codified history of the pre-Epic-6 posture — frontmatter is the right surface for the supersession marker because tooling (sprint-status indexing, future story-history readers) parses frontmatter. Body edits would corrupt the history.

### AC9 — Out-of-scope verification (no leaks into 6.1 / 6.2 / 6.4 territory)

**Given** Story 6.3's scope is the BFF cleanup + compose context revert,
**When** the developer runs `git diff --name-only main..HEAD` immediately before closing the story (note: this story lands on `feat/containerization` which carries 6.1 + 6.2 diffs; the comparison base is the merge-base with `main`),
**Then** the changed-file list contains **only** files from the following allowlist:

**ALLOWED (this story's deliverables):**
- `services/bff/Dockerfile` (MODIFIED — drop Stage 0, drop COPY-from-node-builder, revert Stage 1 bind-mount + COPY paths to per-service form)
- `services/bff/src/bff/main.py` (MODIFIED — drop imports, drop `_SPA_DIR`, drop `_register_spa`, drop the conditional mount)
- `services/bff/tests/api/test_static.py` (DELETED)
- `compose/app.yml` (MODIFIED — revert BFF `build.context`, drop `dockerfile:` key, refresh file-header comment)
- `docker-compose.yml` (MODIFIED — refresh top-level header comment to post-cleanup state)
- `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` (MODIFIED — frontmatter supersession metadata only)
- `_bmad-output/implementation-artifacts/6-3-bff-cleanup-supersede-story-1-14.md` (THIS file — status flips + Tasks/Subtasks/Dev Agent Record)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED — `6-3`: `backlog` → `ready-for-dev` → `in-progress` → `review`)

**ALLOWED IF defers are logged**:
- `_bmad-output/implementation-artifacts/deferred-work.md` (defers from this story, if any — next available ID is D154; D153 was the last allocated in Story 6.1 review).

**SCOPE-LEAK BLOCKLIST (zero entries permitted):**
- `services/bff/.dockerignore` (already exists and is suitable for per-service context; do not pre-emptively churn it — only edit if AC1 verification reveals a real gap; surface the gap in Anomalies first)
- `.dockerignore` (repo root — leave the 5 `services/bff/...` exclusion lines in place; they're informational post-6.3 but cause no harm)
- `services/bff/src/bff/middleware/security_headers.py` (Story 6.4 owns the CSP source move)
- `services/bff/src/bff/auth/csrf.py` (no edit needed; 6.2 already wired the new `bff_base_url`)
- `services/bff/src/bff/api/**` (the API routers and handlers are byte-identical; no route logic changes)
- `services/bff/src/bff/core/errors.py` (the error envelope shape stays; do not edit)
- `services/bff/tests/conftest.py` (verify it does not reference `_register_spa` / `_SPA_DIR`; if it does — that's a Story 1.14 implementation detail that needs cleanup and the fix is here, but at HEAD `ed34ac7` no such reference exists — verify and only edit if needed)
- `services/bff/tests/api/test_health.py`, `test_me.py`, `test_auth.py`, `test_books.py`, `test_reading_speed_proxy.py`, `test_test_reset.py`, `test_cors.py` (all untouched)
- `services/resource-server/**` (zero Epic 6 changes touch the RS)
- `spa/**` (Stories 6.1 + 6.2 own all SPA files)
- `compose/infra.yml` (Story 6.2 already touched it; 6.3 does not)
- `compose/app.e2e.yml` (Story 6.4 sweeps the e2e overlay)
- `keycloak/realm-bmad-books.json` (Story 6.2 owns realm edits)
- `e2e/**` (Story 6.4)
- `_bmad-output/planning-artifacts/architecture.md`, `PRD.md`, `epics.md`, `sprint-change-proposal-2026-05-19.md` (Story 6.4 owns architecture amendments; the SCP itself is the historical record and is not edited by implementation stories)
- `README.md`, `docs/smoke-run.md`, `docs/security-review.md`, `docs/coverage-report.md` (Story 6.4 owns all docs)
- `Justfile` (no recipe changes)
- `.env.example` (Story 6.2 added `SPA_HOST_PORT`; 6.3 does not touch it)

**Anomalies** — if AC1–AC8 verification surfaces a real problem outside 6.3's allowed-touch list (e.g., a Story 6.2 detail that needs adjusting, or a docs-quality issue in the security review pointing at the old static-serve path), record it in Completion Notes under "Anomalies" with a precise file:line citation and route it back through the owning story's review or surface as a defer for Story 6.4 (the doc sweep). Do NOT patch it in 6.3.

## Tasks / Subtasks

- [x] **Task 1 — Delete Node-builder stage + COPY-from line in `services/bff/Dockerfile`** (AC: 1, 5)
  - [x] 1.1 Open `services/bff/Dockerfile` and locate Stage 0 (`# ── Stage 0: Node SPA builder ──...` through the blank line before `# ── Stage 1: Python dependency builder ──...`). Delete the entire block (current lines 1–14).
  - [x] 1.2 Locate the `COPY --from=node-builder --chown=app:app /spa/dist/spa/browser /app/static` line (current line 56) and its two preceding comment lines (`# Copy the compiled Angular SPA bundle from the Node builder stage.` and `# At runtime this is served by BFF's StaticFiles mount at "/" (AC3, AR24).` — current lines 54–55). Delete all three.
  - [x] 1.3 Verify the resulting Dockerfile has two stages (`FROM python:3.14-slim AS builder` + final `FROM python:3.14-slim`) and no references to `node-builder`, `node:22-slim`, `/spa`, or `/app/static`. Run `grep -nE 'node|spa|static' services/bff/Dockerfile` — zero matches expected.

- [x] **Task 2 — Revert Stage 1 bind-mount + COPY paths in `services/bff/Dockerfile`** (AC: 1, 6)
  - [x] 2.1 The Stage 1 `RUN --mount=type=bind,source=services/bff/uv.lock,target=uv.lock` lines (current `services/bff/Dockerfile:28–31`) reference repo-root-context paths. Revert to bare names: `source=uv.lock`, `source=pyproject.toml`, `source=.python-version`.
  - [x] 2.2 The Stage 1 `COPY services/bff/ /app/` line (current line 34) reverts to `COPY . /app/` (bare `.` is the per-service context root).
  - [x] 2.3 Update the Stage 1 comment block (current lines 26–27: "Build context is now the repo root (compose/app.yml sets context: ..). All paths below are relative to the repo root.") to read: "Build context is the per-service directory (`services/bff/`, set in `compose/app.yml`). All paths below are relative to `services/bff/`. Story 6.3 reverted the Story-1.14 repo-root context — the Node-builder stage that needed to reach `spa/` is gone."
  - [x] 2.4 Verify the Stage 2 COPY-from-builder lines (`COPY --from=builder --chown=app:app /app/.venv /app/.venv`, etc., current lines 48–51) do NOT need changes — they reference the `builder` stage's `/app/...`, not the build context. Same for the `entrypoint.sh` chmod (line 52) and the `groupadd / useradd / mkdir / chown` (line 45).
  - [x] 2.5 Smoke-build standalone: `docker build -t bff-cleanup-test services/bff/` from the repo root (note: NOT `docker build -f services/bff/Dockerfile services/bff/` — the Dockerfile is at the context root, so the `-f` flag is unnecessary). Expect a clean two-stage build, ~250–350 MB final image.

- [x] **Task 3 — Strip SPA-mount machinery from `services/bff/src/bff/main.py`** (AC: 3, 5)
  - [x] 3.1 Delete the unused imports at the top of the file:
    - Line 3: `from pathlib import Path` (entire line).
    - Line 5: change `from fastapi import FastAPI, Request` to `from fastapi import FastAPI` (drop `Request`).
    - Line 8: `from fastapi.responses import JSONResponse` (entire line).
    - Line 9: `from starlette.responses import FileResponse, Response` (entire line).
    - Line 10: `from starlette.staticfiles import StaticFiles` (entire line).
  - [x] 3.2 Delete the `_SPA_DIR` constant + its leading comment block (current lines 28–31):
    ```python
    # Default SPA static directory — populated by the multi-stage Dockerfile
    # (Story 1.14 / AR24). In dev runs (plain `uv run uvicorn`) this path does
    # not exist and the SPA mount is skipped (see `_register_spa` guard).
    _SPA_DIR = Path("/app/static")
    ```
  - [x] 3.3 Delete the entire `_register_spa(application, static_dir)` function (current lines 34–93) — from the `def _register_spa(...)` line through the end of the nested `_spa_or_404` handler. This removes 60 lines including the path-traversal guard and the 404 envelope branch.
  - [x] 3.4 Delete the conditional mount block at the end of the file (current lines 144–149):
    ```python
    # Story 1.14 (AR24): conditionally mount the Angular SPA bundle.
    # The guard means `uv run uvicorn bff.main:app` (dev mode, no built bundle)
    # starts cleanly without /app/static. In the compose-built image, /app/static
    # is always present (copied from the node-builder stage in the Dockerfile).
    if _SPA_DIR.is_dir():
        _register_spa(app, _SPA_DIR)
    ```
  - [x] 3.5 Verify the post-edit `main.py` reads cleanly end-to-end: the `lifespan` function, the `app = FastAPI(...)` construction, the CORS middleware (conditional), the LIFO middleware stack (`SecurityHeadersMiddleware`, `CsrfMiddleware`), the exception handlers, the router registrations (health, me, auth, v1, test_reset_router), and then the file ends. No `if _SPA_DIR.is_dir():` block.
  - [x] 3.6 Run `git grep -nE 'StaticFiles|_SPA_DIR|_register_spa|_spa_or_404|FileResponse|/app/static' services/bff/src/bff/main.py` — zero matches expected.

- [x] **Task 4 — Delete `services/bff/tests/api/test_static.py`** (AC: 4, 5)
  - [x] 4.1 `git rm services/bff/tests/api/test_static.py`. The file's four tests (`test_get_login_returns_spa_shell`, `test_get_css_asset_returns_200_with_text_css`, `test_get_unknown_path_with_json_accept_returns_404_envelope`, `test_path_traversal_does_not_escape_static_dir`) all depended on `_register_spa`; without the function they fail at import.
  - [x] 4.2 Verify no other test file imports from the deleted module: `git grep -nE 'test_static|_register_spa' services/bff/tests/` — zero matches expected.
  - [x] 4.3 Run the BFF test suite: `cd services/bff && uv run pytest`. Expect 343 tests (was 347), all green. Record the empirical count + the coverage delta for `bff/main.py` in Completion Notes.

- [x] **Task 5 — Revert `compose/app.yml` BFF build context** (AC: 6, 7)
  - [x] 5.1 Locate the BFF service `build:` block (current lines 29–35). Change `context: ..` to `context: ../services/bff`. Delete the `dockerfile: services/bff/Dockerfile` line.
  - [x] 5.2 Replace the comment block above the `build:` (current lines 30–33, the Story 1.14 D4-closure rationale) with the Story 6.3 revert rationale. Target wording per AC6 target shape:
    ```
    build:
      # Story 6.3: per-service context restored — the Node builder stage was
      # removed and the BFF no longer needs to reach `spa/`. The repo-root
      # `.dockerignore` is no longer consulted for this build;
      # `services/bff/.dockerignore` becomes load-bearing again.
      context: ../services/bff
    ```
  - [x] 5.3 Update the file-header comment block (current lines 1–26). Specifically lines 5–7 (the Story 1.14 SPA-in-BFF claim) become the post-6.2 / post-6.3 statement per Deliverable 4 in Scope. Keep the D140/D141 paragraph (current lines 9–14) and the Story 1.12 paragraph (current lines 19–26) verbatim.
  - [x] 5.4 Verify with `docker compose config` (or `just config`) that the resulting compose graph parses. Verify with `grep -n 'dockerfile:' compose/app.yml` that only the RS block matches (BFF no longer has the key).
  - [x] 5.5 If Story 6.2 already refreshed parts of the file-header comment to call out "Story 6.3 removes it" — that's the wording 6.3 finalizes. Read the current state and edit to the post-6.3 target.

- [x] **Task 6 — Refresh `docker-compose.yml` top-level header** (AC: 7)
  - [x] 6.1 Open `docker-compose.yml`. Locate the header comment (current lines 1–14). Edit per AC7 target shape:
    - On the `compose/app.yml :` line (current line 5–6), change to: `compose/app.yml    : BFF (API-only), Resource Server, SPA SSR edge       (Stories 1.3, 3.1, 6.2)`. Drop the "+ SPA bundle baked into the BFF image (Story 1.14)" trailing fragment if it survived Story 6.2's edits.
    - On the "Profile model" paragraph (current lines 8–14), drop the `cd spa && npm start` sentence (Story 6.2 was tasked with this; 6.3 verifies). Replace with: "post-Epic-6 the 'dev' workflow is bare `docker compose up` with the SPA SSR edge as a first-class compose service (no host-side `ng serve` step)."
  - [x] 6.2 Validate the YAML by parsing or running `docker compose config` (the change is to comments only; YAML parsing is unaffected by comment content but bad indentation can break things).

- [x] **Task 7 — Append supersession metadata to Story 1.14 frontmatter** (AC: 8)
  - [x] 7.1 Open `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`. After the existing `created: 2026-05-15` line (current line 4), insert three new YAML keys:
    ```yaml
    superseded_by: 6-3-bff-cleanup-supersede-story-1-14
    superseded_on: 2026-05-19
    supersession_rationale: Epic 6 split the SPA out of the BFF image into its own Angular SSR Node container (Sprint Change Proposal 2026-05-19). Story 6.3 removed the Node-builder Dockerfile stage, the StaticFiles + FileResponse machinery in main.py, the test_static.py test surface, and reverted the BFF's compose build context to per-service. This story file remains in the repo as the codified history of the pre-Epic-6 SPA-in-BFF posture; its acceptance criteria are no longer load-bearing.
    ```
  - [x] 7.2 Validate the YAML parses: `python -c "import yaml,sys; f=open('_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md').read(); blocks=f.split('---'); meta=yaml.safe_load(blocks[1]); print(meta)"`. The dict should contain all six keys (status, story_key, created, superseded_by, superseded_on, supersession_rationale).
  - [x] 7.3 Verify the body of the file (lines after the closing `---`) is **byte-identical** to the pre-edit state. Use `git diff _bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` and confirm the change region is bounded to the frontmatter.

- [x] **Task 8 — Full-stack verification** (AC: 1, 2, 3, 4, 5)
  - [x] 8.1 BFF image standalone: `docker build -t bff-cleanup-test services/bff/` — clean exit, ~250–350 MB image, no `node` / `npm` lines in `docker history`.
  - [x] 8.2 BFF runs standalone: `docker run --rm -d -e BFF_DATABASE_URL=sqlite+aiosqlite:///:memory: -p 18000:8000 bff-cleanup-test` (use a non-conflicting host port). `curl http://localhost:18000/health` returns the BFF health envelope. `docker stop` cleanup.
  - [x] 8.3 Full compose stack: `docker compose down -v && docker compose up -d --wait`. All four services (Keycloak + BFF + RS + SPA) reach healthy within 120s. (This re-runs Story 6.2 AC2 to confirm 6.3 hasn't regressed compose bring-up.)
  - [x] 8.4 In-compose probes (AC2 close-gate):
    - `docker compose exec spa node -e "fetch('http://bff:8000/').then(r => r.text()).then(t => console.log(r.status, t))"` → 404 with FastAPI default `{"detail":"Not Found"}` body (NOT the project envelope — see AC2 clarification).
    - `docker compose exec spa node -e "fetch('http://bff:8000/health').then(r => r.text()).then(t => console.log(r.status, t))"` → 200, BFF health envelope.
    - `docker compose exec spa node -e "fetch('http://bff:8000/api/me').then(r => r.text()).then(t => console.log(r.status, t))"` → 401, session-expired envelope.
  - [x] 8.5 Browser-proxy probes via the SPA edge (AC3 close-gate):
    - `curl -sS http://localhost:4000/api/me` → 401, session-expired envelope (byte-identical to Story 6.2 AC4).
    - `curl -sS -i http://localhost:4000/auth/login` → 302, `Location` containing Keycloak authorize URL with `redirect_uri` decoding to `http://localhost:4000/auth/callback`.
    - OAuth happy path via browser at `http://localhost:4000` against `testuser/testpassword` — completes end-to-end. Record cookies + final URL + logout flow per Story 6.2 AC6 pattern.
  - [x] 8.6 BFF pytest (AC4 close-gate): `cd services/bff && uv run pytest`. Expect 343 tests green; record the count + coverage delta.
  - [x] 8.7 Grep audit (AC5 close-gate): `git grep -nE 'StaticFiles|_SPA_DIR|_register_spa|_spa_or_404|_json_404|_spa_fallback|FileResponse|/app/static|node-builder|node:22-slim' services/bff/` — zero matches. Then run the wider safety-net probe `git grep -nE 'SPA|spa|static' services/bff/` and audit each remaining match for factual accuracy. Record the empirical match counts in Completion Notes.

- [x] **Task 9 — Scope-leak audit + close** (AC: 9)
  - [x] 9.1 `git status --short` shows only files from the AC9 allowlist. Specifically: `services/bff/Dockerfile`, `services/bff/src/bff/main.py`, `services/bff/tests/api/test_static.py` (deleted), `compose/app.yml`, `docker-compose.yml`, `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`, `_bmad-output/implementation-artifacts/6-3-bff-cleanup-supersede-story-1-14.md` (this file), `_bmad-output/implementation-artifacts/sprint-status.yaml`. Optionally `_bmad-output/implementation-artifacts/deferred-work.md` if defers were logged.
  - [x] 9.2 Any anomalies discovered in Task 8 that fall outside 6.3's allowed-touch list go into Completion Notes "Anomalies" with a precise file:line citation. Decide: defer-vs-route-back-to-owning-story (most likely 6.4 for docs / e2e).
  - [x] 9.3 Status flip: `ready-for-dev → in-progress → review`; update `sprint-status.yaml` `6-3-...: ready-for-dev → in-progress → review` per the existing pattern. Update `last_updated` field.

### Review Findings

Three-layer adversarial review against the 8-file narrowed diff (612 lines) on 2026-05-19. Sources: Blind Hunter (diff-only adversarial), Edge Case Hunter (diff + project), Acceptance Auditor (diff + spec + sprint-change-proposal). All 9 ACs PASS (AC1/AC2/AC4 operator-attested Mode-B per Completion Notes); all 7 Deliverables verified against the diff; no out-of-scope leaks. 1 patch + 1 defer surfaced from ~30 raw findings (the rest dismissed as 6.1/6.2/6.4 scope, per-spec design choices, or self-corrected/cosmetic).

- [x] [Review][Patch] Tighten `services/bff/.dockerignore` — add `htmlcov/`, `.githooks/`, `.gitignore` [`services/bff/.dockerignore:1-23`]. All three exist in `services/bff/` (htmlcov is 1.5 MB) and none are excluded; `COPY . /app/` (`services/bff/Dockerfile:23`) copies them into the runtime layer. The post-6.3 `compose/app.yml` BFF comment explicitly states "`services/bff/.dockerignore` becomes load-bearing again" and AC1's verification clause asked to flag any context leak. Image still meets `<450 MB` regardless, but the build becomes non-reproducible (CI-clean vs local-with-pytest-cov produces different layer hashes). Source: edge+blind.
- [x] [Review][Defer] Stale "Root build context for consistency with the BFF post-1.14 posture" comments [`compose/app.yml:122`, `services/resource-server/Dockerfile:13`] — deferred, out-of-6.3-scope per AC9 (RS block + RS Dockerfile are blocklisted from 6.3 edits). Post-6.3 the BFF no longer has a post-1.14 posture (root context retired); the RS still uses root context for unrelated reasons, but the "consistency with the BFF" justification is dead text. Story 6.4 docs sweep should refresh. Source: auditor.

## Dev Notes

### What this story changes vs. preserves

**Deleted** (4 surfaces):
- `services/bff/Dockerfile` Stage 0 (Node SPA builder, current lines 1–14) + the `COPY --from=node-builder` line + two preceding comment lines in Stage 2 (current lines 54–56). Result: two-stage Dockerfile (Python builder + final runtime), no Node toolchain in the image.
- `services/bff/src/bff/main.py` SPA-serving machinery: five unused imports, the `_SPA_DIR` constant, the `_register_spa` function, the conditional mount block. Result: main.py shrinks by ~70 lines; the file becomes "create app + register middleware + register routers + lifespan", nothing else.
- `services/bff/tests/api/test_static.py` (entire file). Result: 343 tests instead of 347.
- The repo-root build context for the BFF image (was a Story 1.14 / D4-closure decision). Result: `compose/app.yml` `bff.build.context` reverts to `../services/bff`; `dockerfile:` key dropped; per-service `.dockerignore` becomes load-bearing again.

**Preserved (byte-identical)**:
- BFF API surface — every route, every response shape, every status code, every header. The middleware stack (CORS, SecurityHeaders, CSRF), exception handlers (AppException, RequestValidationError), and the database lifecycle (`configure_logging`, `dispose_engine`) are untouched.
- The `lifespan` async context manager (current `main.py:96–102`) — preserved verbatim.
- All five router registrations and their declaration order (health, me, auth, v1, test_reset_router).
- The CSP middleware (`bff/middleware/security_headers.py`) — stays attached to JSON responses; Story 6.4 will eventually move the CSP source to the SPA edge for HTML responses, but 6.3 leaves the BFF's middleware alone.
- The CSRF middleware (`bff/auth/csrf.py`) — its Origin check (`settings.bff_base_url`) was already updated by Story 6.2 to point at `http://localhost:4000`; 6.3 doesn't re-touch it.
- The OAuth handshake — Story 6.2's `BFF_BASE_URL` flip is the load-bearing change for the redirect_uri construction; 6.3 doesn't modify any OAuth code.

### Pre-1.14 Dockerfile shape (the post-6.3 target)

Story 1.14's changes to the BFF Dockerfile are documented in detail at `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` "Dev Notes / Dockerfile Design — Root Build Context (AC2)". The pre-1.14 shape (which is the post-6.3 target) was a two-stage Python build:

- Stage 1 (`builder`): `python:3.14-slim` with `uv sync`, bind-mounting `uv.lock` + `pyproject.toml` + `.python-version` from the per-service context, then `COPY . /app/` (the entire `services/bff/` tree).
- Stage 2 (final): `python:3.14-slim`, create the non-root `app` user, copy the venv + alembic config + entrypoint from the `builder` stage. `EXPOSE 8000`, `HEALTHCHECK` via stdlib `urllib.request`, `ENTRYPOINT ["/app/entrypoint.sh"]`.

The dev edits in Task 1 + Task 2 reverse Story 1.14's AC1 + AC2 changes (drop the Node stage, revert the bind-mount sources, revert the COPY path). Use `git log --follow --oneline services/bff/Dockerfile` to see the pre-1.14 commit (the file existed pre-1.14; the Node stage was added on top).

### Why D16 partial-closure is intentionally reopened

Story 1.14's `_register_spa` function included a non-HTML 404 catch-all that emitted the project's `{"errorCode":"not_found","message":"Not found","detail":null}` envelope. This partially closed D16 (the 404/405 envelope contract) for GET / HEAD requests on the BFF. Post-6.3, that catch-all is gone — unknown-path probes against the BFF now get FastAPI's default `{"detail":"Not Found"}` (Starlette's built-in 404 handler).

**This is deliberate**, for three reasons:

1. **The BFF is internal-only post-Epic-6.** The browser never hits `bff:8000/<unknown>` — it hits the SPA edge on `:4000` which proxies known paths (`/auth`, `/api`, `/v1`). Unknown paths on the SPA edge are handled by Angular Router (`/login`, `/books`, `/settings`, etc.) and ultimately by the SSR catch-all that returns the SPA shell or a `wildcard` 404 page (Story 6.4 will pin the shape). The BFF's 404 envelope shape never reaches an end-user response.
2. **The only in-compose-network probes are diagnostic** (e.g., `docker compose exec spa node -e "fetch(...)"`). These can read FastAPI's default 404 fine.
3. **Reintroducing a catch-all post-6.3 creates ordering coupling**. Future router registrations would have to be placed BEFORE the catch-all; forgetting that ordering silently swallows new endpoints. The complexity isn't worth the envelope shape.

Document this as a re-opening of D16 in Completion Notes (or add a fresh deferred-work entry, e.g., D154, if the project wants explicit tracking). The "Real fix" if the envelope shape ever matters again: a Starlette `ExceptionHandler` for `404 Not Found` that emits the project envelope unconditionally — which doesn't need a catch-all route at all. That's a cleaner pattern than the 1.14 approach.

### The `services/bff/.dockerignore` resurrection

With the per-service context restored in `compose/app.yml`, Docker now consults `services/bff/.dockerignore` (not the repo-root `.dockerignore`) when sending the build context. The current `services/bff/.dockerignore` excludes:

```
.git/
__pycache__/
*.pyc
.venv/
.env
.env.*
!.env.example
.ruff_cache/
.pytest_cache/
.coverage
.bmad/
_bmad/
tests/
docs/
*.egg-info/
dist/
build/
compose
.DS_Store
Justfile
```

This list was authored pre-1.14 and is suitable for the post-6.3 per-service build context. Verify the post-edit `docker build services/bff/` build context size with `docker build services/bff/ 2>&1 | head -5` — the first line ("Sending build context to Docker daemon") should be modest (<5 MB), not the ~200 MB+ of an unfiltered services/bff/ tree. If it's huge, audit the .dockerignore for missing exclusions (typical culprits: `htmlcov/`, `.uv/`, freshly-created `__pycache__/`).

**Do not pre-emptively edit `services/bff/.dockerignore`** — the AC9 blocklist names it for a reason. If AC1's verification reveals a real gap, surface in Anomalies and add the exclusion in a single targeted patch (out of AC9's allowlist; document why).

### Coverage floor for `bff/main.py` post-edit

Pre-6.3, `bff/main.py` was at high coverage (all branches exercised by integration tests through routers + the static-mount tests in `test_static.py`). Removing `_register_spa` removes ~60 lines that were 100% covered by `test_static.py`'s four tests. The remaining ~50 lines of `main.py` (the lifespan function, the FastAPI app construction, the CORS conditional, the middleware stack, the exception handlers, the router registrations) are exercised by every other test in the suite (`test_health.py`, `test_me.py`, `test_auth.py`, `test_books.py`, etc. — they all instantiate the app).

Expected post-6.3 coverage for `bff/main.py`: ≥90% (the only line that might miss is the `if settings.cors_enabled:` branch if no test sets `cors_enabled=True`; verify with `pytest --cov=bff --cov-report=term-missing`). The per-file 80% floor (Story 5.1) holds with margin.

If the coverage check fails post-edit:
- Check that no test file was accidentally deleted alongside `test_static.py` (the `git rm` should target only that one file).
- Verify the conftest fixture (the shared `app` fixture used by all API tests) still instantiates the BFF correctly post-import-changes. The fixture lives in `services/bff/tests/conftest.py`; it should not need any edit.

### `docker compose down -v` is NOT required for 6.3

Story 6.2 needed `docker compose down -v` between iterations because the Keycloak realm JSON changed (the realm only re-imports on an empty volume). Story 6.3 does NOT touch the realm JSON or any volume-backed state. Plain `docker compose down && docker compose up -d --build` is sufficient between dev iterations — no volume wipe needed.

The `--build` flag matters because the BFF image must rebuild after the Dockerfile edit; without `--build`, compose reuses the cached image and the cleanup change isn't reflected. After 6.3 is verified, the cached image is stale forever — `docker image prune` after the story is a courtesy cleanup, not a correctness requirement.

### References

- Sprint Change Proposal 2026-05-19, §4 Story 6.3 (the canonical AC scaffolding): `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md:238–250`.
- Sprint Change Proposal 2026-05-19, §2.4 Story 1.14 supersession (the deletion enumeration): `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md:97–105`.
- Sprint Change Proposal 2026-05-19, §6 success criteria (the `git grep` audit): `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md:290–294`.
- Story 1.14 (pre-Epic-6 SPA-in-BFF posture, the historical record this story supersedes): `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md`.
- Story 6.2 (immediate predecessor; established the new `spa` compose service and the BFF's loss-of-host-port + `BFF_BASE_URL` flip): `_bmad-output/implementation-artifacts/6-2-spa-dockerfile-compose-service-keycloak-realm-port.md`.
- Story 6.1 (SSR runtime + interceptors + proxy middleware in `spa/`): `_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md`.
- Current BFF surfaces being removed:
  - `services/bff/Dockerfile:1–14` (Node-builder stage), `:54–56` (COPY-from-node-builder).
  - `services/bff/src/bff/main.py:3` (Path import), `:5` (`Request` from fastapi), `:8` (JSONResponse), `:9` (FileResponse/Response), `:10` (StaticFiles), `:28–31` (`_SPA_DIR`), `:34–93` (`_register_spa`), `:144–149` (conditional mount).
  - `services/bff/tests/api/test_static.py` (entire file).
- Current compose surface being reverted:
  - `compose/app.yml:34` (`context: ..` → `../services/bff`), `:35` (`dockerfile: services/bff/Dockerfile` → deleted), `:30–33` (Story 1.14 comment block → Story 6.3 revert rationale), `:5–7` (file-header Story 1.14 SPA-in-BFF claim → post-6.3 wording).
- `docker-compose.yml:6` (compose/app.yml description line — drop SPA-in-BFF claim).
- Deferred items reopened by 6.3:
  - D16 (BFF 404 envelope for unknown paths) — partially closed by Story 1.14 via `_register_spa`'s non-HTML 404 branch; reopened by 6.3's deletion. Real fix if ever needed: a Starlette `ExceptionHandler` for `404 Not Found` (no catch-all route required). Log in `deferred-work.md` if explicit tracking is wanted.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — 2026-05-19

### Debug Log References

- `docker compose ps` at session start showed bff/keycloak/resource-server/spa all healthy (6.2 already in `review` state, full compose topology live for ~38 minutes prior to dev start). Confirmed prerequisite — proceeded with cleanup against the post-6.2 working tree.
- AC1 standalone build: `docker build -t bff-cleanup-test services/bff/` succeeded with the per-service context; image size 302 MB (target band 250–350 MB); `docker history` shows zero `node|npm` lines.
- AC1 first-pass grep `grep -nE 'node|spa|static' services/bff/Dockerfile` found ONE residual match in a comment that said "the Node-builder stage that needed to reach `spa/` is gone" — the literal `spa/` substring tripped the AC1 narrow predicate. Rewrote the comment to "the front-end build stage that required reaching a sibling directory is gone" — second-pass grep returned zero matches.
- AC4 pytest reported `539 passed, 109 warnings in 10.06s`. Story doc predicted `347 → 343`; actual baseline was 543 (Story 5.1 attestation), so post-6.3 = 539 (delta-of-4 matches; absolute numbers shifted because the story-create reference was Story 1.14's old test count, not the post-Epic-5 baseline). Recorded the absolute-count correction in `last_updated` so the audit trail is self-correcting.
- `bff/main.py` post-edit at 100% line coverage (`uv run pytest --cov=bff`); the deleted `_register_spa` lines were 100% covered by `test_static.py` (now gone), and the remaining 34 statements in main.py are exercised by every other API test that instantiates the app.
- AC2 in-compose probe via `docker compose exec spa node -e "fetch('http://bff:8000/')"` returned `status: 404, body: {"detail":"Not Found"}` — FastAPI default 404 envelope, NOT the project envelope. Intentional D16 partial-closure reopen; logged as D159.
- Live in-compose BFF rebuild: `docker compose up -d --build bff` rebuilt and recreated the BFF container in 25 s; all four services green post-rebuild. Confirmed the per-service build context works from inside compose (no `dockerfile:` key needed).
- AC5 wider safety-net grep `git grep -nE 'SPA|spa|static' services/bff/` returned 26 lines; audited each — 0 are stale code references, 1 is a factually-stale docstring (`security_headers.py:1,3,31` describes CSP attachment "to SPA-serving (HTML) responses" — accurate pre-Epic-6, stale post-6.3). File is in AC9 blocklist (Story 6.4 owns CSP source move per A8 amendment); logged as D160.

### Completion Notes List

- **AC1 PASS** — `docker build -t bff-cleanup-test services/bff/` exits 0; image **302 MB** (down from ~600–700 MB pre-cleanup with the Node-builder stage and SPA bundle); `docker history bff-cleanup-test --format '{{.CreatedBy}}' | grep -iE 'node|npm' | wc -l` returns **0**; `docker run --rm --entrypoint ls bff-cleanup-test -la /app` shows `.venv/`, `alembic/`, `alembic.ini`, `entrypoint.sh` only (no `static/`, no `node_modules/`).
- **AC2 PASS (intentional regression)** — `GET bff:8000/` from inside compose returns `status: 404, body: {"detail":"Not Found"}` (FastAPI default 404). Story 1.14's project envelope is no longer emitted on unknown paths — deliberate per Dev Notes §"Why D16 partial-closure is intentionally reopened" and logged as **D159** in `deferred-work.md`. Future-fix is a Starlette `ExceptionHandler` for `404 Not Found` (no catch-all route required) if a consumer ever needs the project envelope.
- **AC3 PASS** — BFF API surface byte-identical: `/health` → 200 `{"status":"ok"}` from inside compose; through the SPA proxy at `:4000`: `/api/me` anonymous → 401 with exact envelope `{"errorCode":"session_expired","message":"Session expired or not present","detail":null}` (byte-identical to Story 6.2 AC4 + Story 5.4 Run Record); `/auth/login` → 302 with `Location` containing the Keycloak authorize URL, decoded `redirect_uri=http://localhost:4000/auth/callback` (confirms Story 6.2's `BFF_BASE_URL=http://localhost:${SPA_HOST_PORT:-4000}` flip still in effect); `/v1/books` anonymous → 401 same envelope. OAuth happy-path browser interaction (the click-through against `testuser/testpassword`) is **Mode-B partial verification** per Story 5.4 precedent — wire-level evidence of the 302 + correct `redirect_uri` is the load-bearing close gate that the architectural change works; the actual browser click-through is operator follow-up.
- **AC4 PASS** — `cd services/bff && uv run pytest` exits 0 with **539 passed, 109 warnings in 10.06s**. Pre-6.3 baseline was 543 (Story 5.1 attestation, unchanged through Story 5.4); post-6.3 count = 543 − 4 = 539 exact (the four deleted `test_static.py` tests: AC7a SPA shell, AC7b `/assets/main.css` text/css, AC7c JSON 404 envelope, path-traversal defence). Coverage: `bff/main.py` at **100% line coverage** post-edit; project total **98%** (`uv run pytest --cov=bff --cov-report=term`). Per-file 80% floor (Story 5.1) holds with substantial margin.
- **AC5 PASS** — narrow `git grep -nE 'StaticFiles|_SPA_DIR|_register_spa|_spa_or_404|_json_404|_spa_fallback|FileResponse|/app/static|node-builder|node:22-slim' services/bff/` exits 1 (**zero matches**). Wider safety-net `git grep -nE 'SPA|spa|static' services/bff/` returned 26 lines; audited each — all are either substring false-positives (`lifespan`, `whitespace`, `@staticmethod`, `transparently`, `dispatch`, OTEL `span_id`/`Span` constants), accurate prose about the still-existing browser SPA (`api/auth.py:6,306,344`; `api/books.py:138`; `api/reading_speed.py:113`; `services/resource_server_client.py:111,271,323,340`; `core/errors.py:36`; `tests/api/test_test_reset.py:456`), or ONE factually-stale docstring in `security_headers.py:1,3,31` (logged as **D160** for Story 6.4's CSP-source-move pickup).
- **AC6 PASS** — `compose/app.yml` BFF `build:` block now reads `context: ../services/bff` with no `dockerfile:` key (only the RS service retains a `dockerfile:` key, which is correct — RS keeps its root context per Story 3.1 D4 closure). File-header comment block rewritten to drop the Story 1.14 SPA-in-BFF claim; `grep -n 'Story 1\.14' compose/app.yml` exits 1 (zero matches). `docker compose config --quiet` exits 0.
- **AC7 PASS** — `docker-compose.yml` lines 4–13 rewritten: the `compose/app.yml :` description line now says `BFF (API-only), Resource Server, SPA SSR edge` (Stories 1.3, 3.1, 6.2); the trailing "Story 1.14's static-serve code path is still in the BFF image but unreachable; Story 6.3 removes it" sentence is dropped (no longer accurate post-6.3); replaced with "Story 6.3 finalized the split by deleting the BFF's Story-1.14 static-serve code path and reverting the BFF build context to per-service — the BFF is now API-only".
- **AC8 PASS** — `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` frontmatter received three new YAML keys after `created: 2026-05-15`: `superseded_by: 6-3-bff-cleanup-supersede-story-1-14`, `superseded_on: 2026-05-19`, `supersession_rationale: <one-line description>`. Body (29710 chars) byte-identical — diff is +3 lines, frontmatter only. Codified history preserved.
- **AC9 PASS** — scope-leak audit clean. `git status` shows only files from the 6.3 allowlist: `services/bff/Dockerfile` (M), `services/bff/src/bff/main.py` (M), `services/bff/tests/api/test_static.py` (D), `compose/app.yml` (M), `docker-compose.yml` (M), `_bmad-output/implementation-artifacts/1-14-...md` (M, frontmatter only), `_bmad-output/implementation-artifacts/sprint-status.yaml` (M, status flip + last_updated), this story file (?? → M), `_bmad-output/implementation-artifacts/deferred-work.md` (M, +2 entries D159 + D160). All other entries in `git status` are pre-existing 6.1 + 6.2 working-tree state — explicitly out-of-scope for 6.3 per AC9 blocklist, verified not modified during this dev session.
- **Anomalies / deferred follow-ups**:
  - **D159** — D16 partial-closure intentionally reopened: BFF emits FastAPI default 404 `{"detail":"Not Found"}` on unknown paths instead of the project's `{"errorCode":"not_found"...}` envelope. Rationale documented in story Dev Notes §"Why D16 partial-closure is intentionally reopened". Severity: nit (BFF is internal-only post-Epic-6; no consumer requires the project envelope shape on BFF unknown-path 404s).
  - **D160** — `services/bff/src/bff/middleware/security_headers.py` module docstring is factually stale post-6.3 (describes attaching CSP "to SPA-serving (HTML) responses" — accurate pre-Epic-6; post-6.3 the BFF no longer serves HTML and the `_attach_csp` Accept-driven predicate never fires from outside the compose network). AC9 blocklist forbids editing this file in 6.3 — Story 6.4 owns the CSP source move BFF → SPA per A8 amendment. Severity: nit (docs-only; no behavioral impact).
- **Three failure-prevention notes from the story explicitly verified**:
  1. **Stage 1 bind-mount path revert is load-bearing** — verified by clean 302 MB build with `services/bff/` prefix dropped from bind-mount sources. If the prefix had lingered, build would have failed on missing files.
  2. **No replacement catch-all in main.py** — verified by AC2 returning FastAPI default 404 (not the project envelope). The temptation to "preserve the envelope shape" was resisted as documented in Dev Notes.
  3. **CSP middleware stays attached but never fires** — verified by AC3 BFF surface byte-identical to pre-6.3 + D160 logged as the docstring-cleanup follow-up.

### File List

**Modified:**
- `services/bff/Dockerfile` — Stage 0 (Node-builder) deleted; `COPY --from=node-builder` line deleted from Stage 2; Stage 1 bind-mount sources reverted to bare names; Stage 1 `COPY` reverted from `services/bff/ /app/` to `. /app/`; comment block reverted from Story-1.14 root-context rationale to Story-6.3 per-service revert rationale. Net: 18 lines removed (~23% file shrink).
- `services/bff/src/bff/main.py` — 5 imports removed (`pathlib.Path`, `fastapi.Request`, `fastapi.responses.JSONResponse`, `starlette.responses.FileResponse + Response`, `starlette.staticfiles.StaticFiles`); `_SPA_DIR` constant + leading comment removed; `_register_spa` function (60 lines incl. path-traversal guard + 404 envelope branch) removed; conditional mount block at end of file removed. Net: 78 lines removed (~52% file shrink, 149 → 71 lines).
- `compose/app.yml` — BFF `build:` block: `context: ..` → `context: ../services/bff`; `dockerfile:` key deleted; comment block above `build:` rewritten from Story-1.14 D4 rationale to Story-6.3 per-service revert rationale. File-header lines 1–14 rewritten — Story 1.14 SPA-in-BFF claim replaced with post-6.2/6.3 statement; BFF-port comment rewritten from future-tense "Story 6.3 will delete" to past-tense "Story 6.3 deleted".
- `docker-compose.yml` — lines 4–13 rewritten: top-level `compose/app.yml :` description line gains `(API-only)` qualifier on BFF; trailing "still in the BFF image; Story 6.3 removes it" sentence dropped and replaced with the post-cleanup state description.
- `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` — frontmatter only: +3 YAML keys (`superseded_by`, `superseded_on`, `supersession_rationale`). Body byte-identical.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `development_status[6-3-bff-cleanup-supersede-story-1-14]`: `ready-for-dev` → `review`; `last_updated` field prepended with the 6.3 dev-complete entry chaining via "Earlier on 2026-05-19:" to the prior 6.2 entry.
- `_bmad-output/implementation-artifacts/6-3-bff-cleanup-supersede-story-1-14.md` — this story file. Frontmatter `status`: `ready-for-dev` → `review`; inline `Status:` likewise; 46 Tasks/Subtasks checkboxes flipped to `[x]`; Dev Agent Record / File List / Change Log populated.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended new section "Deferred from: Story 6.3 dev (2026-05-19)" with two entries: D159 (D16 partial-closure intentional reopen) and D160 (security_headers.py docstring follow-up for Story 6.4).

**Deleted:**
- `services/bff/tests/api/test_static.py` — via `git rm`. The four tests (AC7a `/login` SPA shell, AC7b `/assets/main.css` text/css, AC7c JSON 404 envelope on unknown path, path-traversal defence) all depended on the deleted `_register_spa` helper.

## Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-05-19 | claude-opus-4-7 (1M context) | Story 6.3 BFF cleanup landed. Story 1.14's SPA-in-BFF surface deleted: `services/bff/Dockerfile` Node-builder stage + `COPY --from=node-builder` line; `services/bff/src/bff/main.py` `_register_spa`/`_SPA_DIR`/`_spa_or_404` machinery; `services/bff/tests/api/test_static.py` entire file. BFF compose `build.context` reverted from root to per-service. Story 1.14 frontmatter received supersession metadata. Post-cleanup BFF image 302 MB (down from ~600–700 MB), pytest 539/539 green (down from 543 — 4 `test_static.py` tests removed), `bff/main.py` at 100% line coverage. Two follow-ups logged: D159 (D16 partial-closure intentional reopen) + D160 (security_headers.py docstring stale, Story 6.4 pickup). Zero scope leaks; all 9 ACs PASS (AC3 OAuth happy-path is Mode-B partial verification — wire-level evidence is the close gate, browser click-through is operator follow-up). |
