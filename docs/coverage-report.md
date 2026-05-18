# Coverage Report

**Run date:** 2026-05-18
**Commit SHA:** `3e3612a` (`3e3612ac46d852fd14a4d3dbbd453ffd78c3e51b`) — the Story 4.4 merge tip; Epic 1–4 fully closed before this audit.
**Status:** All thresholds met
**Authored by:** Story 5.1 (Coverage audit + gap-fill)

## Reproduce

```bash
cd services/bff               && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html
cd services/resource-server   && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html
cd spa                        && npm test -- --coverage
# E2E (spec-count surface — no line coverage):
just e2e-up
# …or, if `just` is unavailable, the inlined recipe (matches the Justfile's set -e + trap EXIT semantics so Ctrl-C / failure paths still tear the stack down):
bash -c 'set -e
  trap "docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e down" EXIT
  docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up -d --wait keycloak bff resource-server
  docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e run --rm --build playwright
'
```

The Python `pytest-cov` invocations write HTML to `services/bff/htmlcov/index.html` and `services/resource-server/htmlcov/index.html`. The SPA `--coverage` flag writes HTML to `spa/coverage/spa/index.html` (Angular's `@angular/build:unit-test` builder nests the report one directory deeper than raw Vitest defaults). All three HTML directories are gitignored.

## Targets

| Surface | Aggregate target | Per-file floor | Source |
|---------|------------------|----------------|--------|
| BFF     | ≥90% line        | ≥70% line      | archetype (`services/bff/pyproject.toml:86` `fail_under = 90` at default `precision = 0`; effective floor ~89.5% rounded); per-file floor pinned by Story 5.1 |
| RS      | ≥90% line        | ≥70% line      | archetype (`services/resource-server/pyproject.toml:112` `fail_under = 90` at default `precision = 0`); per-file floor pinned by Story 5.1 |
| SPA     | ≥70% on each of statements / branches / functions / lines | ≥50% lines per file | PRD NFR11 / architecture line 272 |
| E2E     | ≥5 specs covering J1–J6 | n/a       | PRD NFR11 / `_bmad-output/planning-artifacts/epics.md` NFR11 |

## BFF

- **Aggregate line coverage:** **97.26%** (1421/1461 statements covered; 40 missed)
- **Test count:** 543 passed in 10.15s
- **Per-file scores below 70%:** none
- **Lowest per-file:** `src/bff/core/database.py` at **84%** (8 missed of 50 statements — lines 27-29, 48, 53-55, 79; engine-bootstrap and disposal paths exercised only at process lifecycle, not in unit tests)
- **Other per-file scores below 95%:** `src/bff/core/config.py` 91% (pydantic-settings env-resolution branches); `src/bff/main.py` 92% (FastAPI lifespan glue); `src/bff/auth/csrf.py` 94%; `src/bff/auth/keycloak_cookie_session.py` 97%; `src/bff/api/auth.py` 96%
- **Excluded modules (`[tool.coverage.run] omit`):** none — `services/bff/pyproject.toml:82-83` declares only `source = ["src"]`; the BFF has carried no exclusion list since Story 1.3.

## RS

- **Aggregate line coverage:** **98.33%** (826/840 statements covered; 14 missed)
- **Test count:** 324 passed in 8.34s
- **Per-file scores below 70%:** none
- **Lowest per-file:** `src/resource_server/auth/factory.py` at **77%** (7 missed of 31 statements — lines 30, 38-45, 55; archetype-emitted scaffolding paths consumed only by the unused Azure-AD branch)
- **Other per-file scores below 100%:** `src/resource_server/auth/dependencies.py` 96% (lines 37, 46); `src/resource_server/core/database.py` 90% (lines 27-29, 48, 70 — same engine-bootstrap pattern as BFF)
- **Excluded modules (`[tool.coverage.run] omit` — preserved from Story 3.1):**
  - `**/mock_*.py` — archetype-emitted mock helpers (dead in production).
  - `src/resource_server/auth/entra.py` — archetype's Azure-AD bearer module; replaced by `oidc_bearer.py` in Story 3.2.
  - `src/resource_server/observability/otel.py`, `observability/prometheus.py` — archetype-emitted OTEL + Prometheus wiring; kept on disk for documentation parity, never invoked from `main.py` (sprint-change 2026-05-14 + AR1 archetype-mandate note).
  - `src/resource_server/core/constants.py`, `factories/__init__.py`, `models/dto/__init__.py`, `models/dto/v1/__init__.py` — archetype-emitted module-level constants / thin re-exports; no behavior consumed by RS surface.
- **No additions to the omit list in Story 5.1.**

## SPA

- **Aggregate (statements / branches / functions / lines):** **94.71% / 91.16% / 95.74% / 94.52%** (699/738, 382/419, 90/94, 535/566 respectively)
- **Test count:** 152 passed across 19 test files in 1.54s
- **Per-file lines below 50% (hard floor):** none
- **Lowest per-file lines:** `app/shared/errors/error-service.ts` at **78.94%** (uncovered `case` branches within lines 82-96 — the `forbidden_scope` / `csrf_invalid` / `auth_state_invalid` / `book_not_found` / `invalid_input` case-return pairs are not yet exercised by a dedicated test; the three cases the SPA currently relies on — `session_expired`, `reading_speed_unset`, `resource_server_unavailable` — are covered)
- **Other per-file lines below 90%:** `app/books/estimate-cell.ts` 86.66% (lines 86, 129, 142-143); `app/books/status-control.ts` 88.88% (lines 83-84); `app/books/estimate-cell.html` 90.47% (template branches 14, 33); `app/books/book-row.ts` 90.9% (lines 108-109); `app/books/book-form.ts` 93.75% (5 lines)
- **Excluded patterns (Vitest `coverage.exclude`):** none added in Story 5.1. Coverage is collected via Angular's `@angular/build:unit-test` builder using Vitest v8 defaults; `*.types.ts` files emit no JavaScript and therefore do not appear in the coverage matrix.

## E2E

- **Spec count:** **6 files / 26 tests** covering J1–J6 — `j1-first-login.spec.ts` (3), `j2-manage-books.spec.ts` (8), `j3-estimate.spec.ts` (5), `j4-adjust-speed.spec.ts` (5), `j5-logout.spec.ts` (2), `j6-rs-unavailable.spec.ts` (3). NFR11's "≥5 covering J1–J6" satisfied.
- **`workers: 1`** invariant preserved (`e2e/playwright.config.ts:15`; load-bearing because every spec's `beforeEach resetState(...)` would race under parallel workers).
- **Live `--profile e2e` run** at `3e3612a` (inlined Justfile recipe; `just` not installed on the audit host): **26 passed (53.0s)**.
  - Per-journey breakdown matches expected: J1×3 ✓, J2×8 ✓, J3×5 ✓, J4×5 ✓, J5×2 ✓, J6×3 ✓.
  - Cleanup via `trap … EXIT` succeeded: keycloak / bff / resource-server stopped + removed; network removed.

## Method

- **BFF / RS:** `pytest-cov` (≥6.0) against `src/<svc>/`. The `omit` list is preserved verbatim from each service's `pyproject.toml`; no new omissions added in Story 5.1. The `--cov-report=term-missing` output is the source of truth for the "Missing" line numbers cited above.
- **SPA:** Vitest 4.1 + `@vitest/coverage-v8` 4.1.6 via the `@angular/build:unit-test` builder. The text reporter emits the four metrics independently; the per-file table above is verbatim from the reporter's output. No `coverage.exclude` overrides — the Angular builder's default include set is the active configuration.
- **E2E:** not instrumented for line coverage. The rule is a spec-count rule per NFR11; the "≥5 covering J1–J6" gate is satisfied by 6 specs. The live `--profile e2e` run is the load-bearing close gate (retro P2 from `epic-1-retro-2026-05-16.md`) — passing static `npx playwright test --list` is necessary but not sufficient.

## Gaps closed in this run

None. All thresholds were already met as of the Story 4.4 close (`3e3612a`); Story 5.1 added no tests, no `omit` entries, and no `coverage.exclude` patterns. The audit is an attestation that:

- The BFF (97.26%) and RS (98.33%) aggregates exceed the archetype's `fail_under = 90` by ≥7 percentage points.
- The SPA (94.71% / 91.16% / 95.74% / 94.52%) exceeds the PRD's ≥70% floor on all four metrics by ≥21 percentage points.
- No file on any surface falls below the per-file floor (≥70% backend lines, ≥50% SPA lines).
- The E2E spec count (6) exceeds the NFR11 floor (5), with the live run green.

## Notes on per-file gaps (informational, not actioned)

Several files have non-100% coverage that, while above the per-file floor, are worth surfacing as the natural follow-ups for future test-quality passes:

- **`services/bff/core/database.py` (84%)** and **`services/resource-server/core/database.py` (90%)** — engine bootstrap + disposal paths (`init_engine`, lifecycle on close). Exercised in integration but not in unit tests. Belongs to: backend lifecycle test pass.
- **`services/resource-server/auth/factory.py` (77%)** — archetype scaffolding that branches to the unused Azure-AD provider. The 7 missing statements all live on the Azure-AD code path the RS does not consume.
- **`spa/src/app/shared/errors/error-service.ts` (78.94% lines)** — `parse()` branches for error envelope shapes not yet emitted by the BFF (defensive coverage of `unknown` / fallback paths). The branches the SPA currently relies on (412 reading_speed_unset, 503 resource_server_unavailable, 401 session_expired) are 100% covered.
- **`spa/src/app/books/estimate-cell.ts` (86.66% lines)** — lines 86 (`onEstimateClick` cancellation guard), 129 (estimate-result invariant guard), and 142-143 (defensive `if (error)` branch when `result` is non-null) live behind invariants that the surrounding code prevents.

These are deliberate test-quality polish items, not coverage gaps. None require action under Story 5.1's scope; if Story 5.2 / 5.3 audit them as part of the security/README polish work they can be addressed there.
