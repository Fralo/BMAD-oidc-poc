---
status: done
story_key: 5-1-coverage-audit-gap-fill
epic: 5
prerequisites: 1.1–1.14 (Epic 1 — Foundation, all done); 2.1–2.7 (Epic 2 — Books, all done); 3.1–3.6 (Epic 3 — Reading Speed, all done); 4.1–4.4 (Epic 4 — Estimate + Honest Failure, all done after 4.4 code-review pass). E2E spec coverage: 6 files / 26 tests across J1–J6 (NFR11 satisfied by 4.4's close gate). BFF + RS pyproject.toml already declare `fail_under = 90` (`services/bff/pyproject.toml:86`, `services/resource-server/pyproject.toml:112`). SPA Vitest coverage installed (`spa/package.json:31` = `@vitest/coverage-v8`; existing script `npm run test:coverage` → `ng test --coverage`).
created: 2026-05-18
baseline_commit: 3e3612a
---

# Story 5.1: Coverage audit + gap-fill

Status: done

<!-- Sprint: Epic 5 (Final Coverage Push & Security Review). First story in Epic 5. -->
<!-- Follows: Story 4.4 (E2E specs J3 + J6 — done). Precedes: Story 5.2 (Security review document). -->

## Story

As a maintainer preparing the project for review,
I want a coverage audit across all four code surfaces (BFF, RS, SPA, E2E) with any gaps below threshold filled by targeted tests,
So that NFR11 (≥70% SPA / archetype's >90% backend / ≥5 E2E covering J1–J6) is provably met at handoff.

## Scope (read this first)

This story is **mostly measurement + reporting** — run the existing coverage tooling on three surfaces, write a single new doc (`docs/coverage-report.md`), reference it from the README, and **only if a gap exists** add targeted tests in the source-mirroring location. The four surfaces are not all at the same maturity:

- **BFF.** As of Story 4.2 close (commit `b905307`): **97.26%** project coverage (story 4.2 DAR). Per-module coverage was confirmed `100%` on `resource_server_client.py`. The project is in compliance with `fail_under = 90`. Expectation: zero or near-zero new tests needed; the gap report is mostly an attestation.
- **RS.** No project-level coverage figure has been captured in any story DAR. Per-endpoint per-file coverage was checked story-by-story (Stories 3.3, 3.4, 4.1) but the aggregate has never been published. Expectation: re-run and report; very likely already in compliance because every endpoint has been test-driven, but a few archetype-emitted modules may surface that should either be exercised or added to the `omit` list with justification.
- **SPA.** Story 4.3 DAR reports a per-file slice (`estimate-cell.ts` 88.23%/78.57%; `books-service.ts` 100%/85%); no aggregate has been published. Story 1.8 / 2.4 / 3.5 / 4.3 each grew the surface; the aggregate has not been measured against the ≥70% NFR floor. Expectation: small targeted backfills may be needed, especially around utility / interceptor / route-config modules that were never the focus of any one story.
- **E2E.** No coverage instrumentation — Playwright runs against the deployed binary. NFR11 here is the **spec-count** rule: ≥5 specs covering J1–J6. As of Story 4.4 close: **6 spec files / 26 tests** covering J1×3, J2×8, J3×5, J4×5, J5×2, J6×3. The AC8 for this story is a structural assertion that those 6 files exist and the live `--profile e2e` run is green.

Concretely, this story delivers:

1. **`docs/coverage-report.md`** (NEW) — single source of truth for the current coverage snapshot. Format detailed in AC2.
2. **README.md reference** (MODIFY) — one line under an appropriate section pointing at `docs/coverage-report.md`.
3. **Gap-fill tests** (CONDITIONALLY ADD) — only if a per-surface aggregate or per-file score falls below threshold. Each new test lives in the source-mirroring path per architecture's Naming Patterns (`services/<svc>/tests/<mirror>` for backend, `<source>.spec.ts` colocated for SPA).
4. **`omit` / `coverage.exclude` justifications** (CONDITIONALLY ADD) — any deliberate exclusion (generated migration, archetype dead-module, pydantic-settings bootstrap glue) is named in the report AND reflected in the relevant config (`[tool.coverage.report] omit` for Python, Vitest `coverage.exclude` for SPA), with the justification echoed as a comment near the config entry.

Out of scope:

- **Story 5.2** (security review document at `docs/security-review.md`) — separate story.
- **Story 5.3** (README polish + AI integration log) — the README touch in this story is a single reference line; the full README rewrite is 5.3's job.
- **Story 5.4** (final `docker compose up` smoke at `docs/smoke-run.md`) — separate story.
- **Pre-existing SPA lint failures D127** (`no-fallthrough` on `book-form.ts:218`, `book-row.ts:104`, `status-control.ts:79`) — lint, not coverage. Out of scope; do NOT fix here.
- **Deferred items D113–D118, D121–D126** (test-quality items raised by 4.1 / 4.2 code review) — they are documented test polish, not coverage gaps. Only address them if (a) they overlap a real coverage gap surfaced by this audit, or (b) the audit reveals that fixing them is the cheapest path to threshold.
- **Latency or perf testing** — not part of NFR11.
- **Migrating coverage tooling** (e.g., adding nyc or replacing vitest) — out of scope; reuse what is installed.

## Acceptance Criteria

### AC1 — Three coverage commands run to completion

**Given** the maintainer is at the repo root after Epics 1–4 have shipped,
**When** the developer runs the per-surface coverage commands:

```bash
cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html
cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html
cd spa && npm test -- --coverage
```

**Then** each command runs to completion and produces:

- A **terminal summary** (line, branch, function/methods totals — per the runner's default reporter).
- An **HTML report** at `services/bff/htmlcov/index.html`, `services/resource-server/htmlcov/index.html`, and `spa/coverage/spa/index.html` (Angular's `@angular/build:unit-test` builder wraps Vitest and nests the report one directory deeper than raw Vitest defaults).

**Verification:** each command exits 0; each HTML index file exists after the run.

**Notes:**
- The BFF and RS commands use the **same coverage source line** that already exists in `pyproject.toml`: `[tool.coverage.run] source = ["src"]` on the BFF (line 83); on the RS the existing `omit` list (lines 100-109) is preserved.
- For the SPA the `npm test -- --coverage` invocation forwards `--coverage` to the existing `ng test` script; `@vitest/coverage-v8` is already a devDependency (`spa/package.json:31`). An equivalent `npm run test:coverage` exists as an alias and may be used — same end result; the report's "How to reproduce" section names the canonical form (`npm test -- --coverage`) but accepts the alias.
- Use the `--cov-report=term-missing` form for both Python services — the `term-missing` output is what the gap report quotes for any per-file score below threshold.

### AC2 — `docs/coverage-report.md` exists with one section per surface

**Given** the gap report file `docs/coverage-report.md` exists,
**When** the developer inspects it,
**Then** it contains the following structure:

```markdown
# Coverage Report

**Run date:** YYYY-MM-DD
**Commit SHA:** <full SHA or first 7 chars from `git rev-parse HEAD`>
**Status:** All thresholds met  <-- or e.g. "All thresholds met with documented exclusions" if any omit/exclude entries were added

## Reproduce

cd services/bff               && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html
cd services/resource-server   && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html
cd spa                        && npm test -- --coverage
cd e2e                        && docker compose --profile e2e up --abort-on-container-exit   # (spec-count surface; see §E2E)

## Targets

| Surface | Aggregate target | Per-file floor | Source |
|---------|------------------|----------------|--------|
| BFF     | ≥90% line        | ≥70% line      | archetype (pyproject `fail_under = 90` at default `precision = 0`; effective floor ~89.5% rounded); per-file floor pinned by this story |
| RS      | ≥90% line        | ≥70% line      | archetype (pyproject `fail_under = 90` at default `precision = 0`; effective floor ~89.5% rounded); per-file floor pinned by this story |
| SPA     | ≥70% statements/branches/functions/lines | ≥50% any single file | PRD NFR11 / architecture §"Testing Framework" line 272 |
| E2E     | ≥5 specs covering J1–J6 | n/a       | PRD NFR11 / epics.md NFR11 line 38 |

## BFF

- Aggregate line coverage: NN.NN%
- Per-file scores below 70%: (none) | (list with score + reason)
- Excluded modules (`[tool.coverage.run] omit`): (none) | (named list with one-line justification each)

## RS

- Aggregate line coverage: NN.NN%
- Per-file scores below 70%: (none) | (list)
- Excluded modules (`[tool.coverage.run] omit`): (named list — preserved from Story 3.1 + any new additions justified here)

## SPA

- Aggregate (statements / branches / functions / lines): NN.NN% / NN.NN% / NN.NN% / NN.NN%
- Per-file scores below 50% (hard floor): (none) | (list)
- Per-file scores below 70% (informational): (list — counted toward the aggregate but not a hard fail)
- Excluded patterns (Vitest `coverage.exclude`): (named list — only if any were added)

## E2E

- Spec count: 6 files / 26 tests covering J1–J6 (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3 as of `3e3612a`).
- Live run command: `just e2e-up` (or `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e up --abort-on-container-exit`).
- Last green: <date / commit SHA> — captured from this story's regression run.

## Method

- BFF / RS: pytest-cov against `src/<svc>/`. The `omit` list is preserved verbatim from each service's `pyproject.toml` and any new omission is justified inline below AND mirrored in `pyproject.toml` with a matching comment.
- SPA: Vitest v8 coverage. Excludes (if any) are mirrored into `vitest.config.ts` (or `angular.json` test target if that is where coverage config lives — confirm at run time and write in whichever file it actually applies).
- E2E: not instrumented (no line coverage); the rule is a spec-count rule per NFR11.

## Gaps closed in this run

(One line per added test file: path + AC# from this story it addresses. Empty if none needed.)
```

**And** it records the date of the run (`run date`) and the commit SHA the run was made against (use `git rev-parse HEAD` at the moment of the snapshot; this should be the commit that holds the new tests if any were added).

**And** the report is referenced from the README under an appropriate section (see AC8).

### AC3 — Any below-threshold files are filled in source-mirroring locations

**Given** the gap report identifies files below threshold,
**When** the developer adds targeted tests in the source-mirroring location per architecture's Naming Patterns:

- Backend: a function in `services/<svc>/src/<svc>/services/foo.py` is tested by `services/<svc>/tests/services/test_foo.py` (architecture line 615). **Do NOT** invent a new top-level test directory; **do NOT** place backend tests under `tests/utils/` for code that lives in `src/<svc>/services/` (anti-pattern called out at architecture line 858).
- SPA: a component / service at `spa/src/app/<feature>/<name>.ts` is tested by `spa/src/app/<feature>/<name>.spec.ts` colocated next to the source (architecture line 576).

**Then** re-running the relevant coverage command shows all files at or above threshold,
**And** the gap report is regenerated with no remaining unaddressed gaps,
**And** any deliberate exclusions are listed with justification and reflected in the relevant tool config:

- **Python:** add the file path to `[tool.coverage.report] omit` in the relevant `pyproject.toml` (RS already has this pattern at lines 100–109; BFF currently has none). Add a code comment block above the entry stating the reason, mirroring the RS pattern.
- **SPA:** add a glob to Vitest's `coverage.exclude` (typically in `vitest.config.ts`; if the project uses Angular's builder-managed config, that may be in `angular.json` under `test.options` — confirm the actual location at run time and update wherever Vitest resolves it from). Document the exclusion in `docs/coverage-report.md` AND inline near the config entry.

### AC4 — SPA aggregate ≥70% on all four metrics + hard per-file floor

**Given** the SPA coverage target is ≥70%,
**When** `npm test -- --coverage` is run,
**Then** the summary reports **≥70% on statements, branches, functions, AND lines** (all four standard metrics — falling below on any single one is a failure),
**And** no per-file score is below 50% on lines (hard floor: a single 0-coverage file is a process failure surface and the report MUST surface it).

**Notes:**
- The four-metric rule is verbatim from epic AC line 1777. Vitest's default text reporter emits all four; the gap report cites the line for each.
- Files that exist for type-only purposes (`*.types.ts` — `book.types.ts`, `auth.types.ts`, `estimate.types.ts`, `reading-speed.types.ts`, `app-error.types.ts`) emit no JavaScript and should not appear in the coverage matrix at all. If they do (depending on tsc emit), they may be excluded via Vitest's `coverage.exclude` glob `**/*.types.ts` — justified inline in both the config and the report.
- `app.config.ts` / `app.routes.ts` / `app.ts` (Angular bootstrap) are typically not unit-tested directly — exercising them in integration is sufficient. If they fall below the 50% per-file floor, exclude them with the same pattern + justification.
- Existing test file count = 19 (`Test Files 19 passed` per 4.4 DAR); existing test count = 152.

### AC5 — BFF aggregate ≥90% + per-file ≥70%

**Given** the BFF coverage target is ≥90% (per archetype, `fail_under = 90` at default `precision = 0`),
**When** `uv run pytest --cov=src/bff --cov-report=term-missing` is run inside `services/bff/`,
**Then** the summary reports **≥90% line coverage** as enforced by the archetype's `fail_under = 90` (with the default `precision = 0`, coverage.py's gate is `round(total, 0) < 90`, so the effective floor is ~89.5%; verify by reading the pytest-cov exit code, which is non-zero on threshold failure),
**And** no per-file score is below 70%.

**Notes:**
- BFF baseline as of Story 4.2 close = 97.26% (DAR `chore(4.2)`). Story 4.3 (SPA-only) and Story 4.4 (E2E-only) added no BFF code or BFF tests, so the BFF figure should be unchanged from `b905307` → `3e3612a`. If the audit surfaces a drop, the most likely cause is an unrelated regression and the dev should triage as a real defect (this story would still close once coverage is back above threshold).
- The `[tool.coverage.run] omit` list on the BFF is **empty today** (`services/bff/pyproject.toml:82-83` has only `source = ["src"]`). If a justified omission emerges, add it with the same comment pattern that the RS uses (lines 82-99) — one paragraph naming the module, its reason for exclusion, and the story that introduced it.

### AC6 — RS aggregate ≥90% + per-file ≥70%

**Given** the RS coverage target is ≥90% (per archetype, `fail_under = 90` at default `precision = 0`),
**When** `uv run pytest --cov=src/resource_server --cov-report=term-missing` is run inside `services/resource-server/`,
**Then** the summary reports **≥90% line coverage** (effective floor ~89.5% rounded — same semantics as AC5),
**And** no per-file score is below 70%.

**Notes:**
- No project-level RS coverage figure has been captured in any prior story. The per-endpoint coverage (Stories 3.3 estimate, 3.4 reset, 4.1 estimate) has each been spot-checked.
- The existing `omit` list (lines 100-109) excludes seven archetype-emitted dead modules — confirmed unchanged since Story 3.1. Do not remove any of these omissions in this story.
- If new modules are surfaced (e.g., `auth/factory.py`, `auth/role_mapping.py`, `auth/contracts.py`, `auth/models.py`, `auth/dependencies.py`, `auth/none.py`) below 70%, the choice is: add targeted tests OR add to `omit` with justification. Default to **add tests** unless the module is purely a re-export / archetype scaffolding that the project does not consume. Compare against the BFF pattern where the `auth/` subpackage is exercised through the integration boundary.
- The RS CLAUDE.md (`services/resource-server/CLAUDE.md`) requires `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, AND the full test suite to pass before commit. New RS tests must satisfy all four.

### AC7 — E2E spec-count rule satisfied (no coverage instrumentation)

**Given** the E2E project at `e2e/`,
**When** the maintainer reviews `e2e/tests/`,
**Then** spec files exist covering every PRD journey:

- `e2e/tests/j1-first-login.spec.ts` (Story 1.13 — 3 tests)
- `e2e/tests/j2-manage-books.spec.ts` (Story 2.7 — 8 tests)
- `e2e/tests/j3-estimate.spec.ts` (Story 4.4 — 5 tests)
- `e2e/tests/j4-adjust-speed.spec.ts` (Story 3.6 — 5 tests)
- `e2e/tests/j5-logout.spec.ts` (Story 1.13 — 2 tests)
- `e2e/tests/j6-rs-unavailable.spec.ts` (Story 4.4 — 3 tests)

All 6 files present from Epics 1–4 (verify by `ls e2e/tests/`),
**And** `docker compose --profile e2e up --abort-on-container-exit` (or equivalently `just e2e-up`) passes the full suite with exit code 0,
**And** `playwright.config.ts` preserves `workers: 1` (sequential — `resetState` requires this; verified by reading `e2e/playwright.config.ts:14-15`).

**Notes:**
- `just e2e-up` was upgraded in Story 4.4 to pass `--build` to `docker compose run` (handles the `COPY . .` cached-image trap). Use `just e2e-up` as the canonical command; the spec-by-spec `npx playwright test` form remains valid for dev iteration but is NOT what the audit runs.
- The 26 test breakdown (J1×3, J2×8, J3×5, J4×5, J5×2, J6×3) is the audit's pinned expected output. If the live run reports a different total, that is itself a defect the audit must surface in `docs/coverage-report.md` under "E2E discrepancies".

### AC8 — README references the gap report

**Given** the gap report at `docs/coverage-report.md` exists,
**When** the developer updates `README.md`,
**Then** the README contains at least one reference to `docs/coverage-report.md`, placed under either the "Architecture overview" section (after the existing architecture.md link) OR a new "Testing" section (one-paragraph stub if added).

**Notes:**
- Do NOT rewrite the README in this story. Story 5.3 owns the full README rewrite. The reference here is a single line so that the report is naturally discoverable when 5.3 picks up.
- Acceptable placements (pick one — do not duplicate):
  - After the existing `architecture.md` link in the "Architecture overview" section.
  - As a new sub-heading `### Coverage` right after the "E2E profile" section.
- The reference itself: `See [`docs/coverage-report.md`](docs/coverage-report.md) for the per-surface coverage snapshot and thresholds.`

### AC9 — Status line reads "All thresholds met"

**Given** every gate is green,
**When** the developer commits the gap report,
**Then** the report's "Status" line reads `**Status:** All thresholds met` (or, if any exclusions were added during this story, reads `**Status:** All thresholds met with documented exclusions` and the relevant section lists them).

**Anti-pattern:** the status line MUST NOT read "All thresholds met" if any per-surface aggregate is below threshold, even if every per-file score is. The aggregate rules in AC4 / AC5 / AC6 are hard fails on the aggregate.

## Tasks / Subtasks

- [x] **Task 1 — Bring up + run BFF coverage (AC1, AC5)**
  - [x] 1.1 `cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html`. Capture the aggregate line %, the per-file table, and the `term-missing` output verbatim.
  - [x] 1.2 If aggregate ≥90% AND no per-file <70%: record the figures; no test additions. Proceed. ← **path taken** (97.26% aggregate, lowest per-file 84%)
  - [x] 1.3 N/A — Task 1.2 path met threshold; no BFF tests added.
  - [x] 1.4 N/A — no exclusions added.

- [x] **Task 2 — Bring up + run RS coverage (AC1, AC6)**
  - [x] 2.1 `cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html`. Captured: 98.33% aggregate / 324 tests / lowest per-file `auth/factory.py` at 77%.
  - [x] 2.2 N/A — Task 2.1 path met threshold; no RS tests added.
  - [x] 2.3 N/A — no additions to the existing `omit` list (Story 3.1's seven-entry block preserved verbatim).
  - [x] 2.4 N/A — no new RS test files created, so the ruff/ty gate is not exercised in this story. (Existing RS suite already passes per Story 4.1 commit `19cb3f8` baseline.)

- [x] **Task 3 — Bring up + run SPA coverage (AC1, AC4)**
  - [x] 3.1 `cd spa && npm test -- --coverage`. Captured: 94.71% / 91.16% / 95.74% / 94.52% (statements / branches / functions / lines); 152 tests across 19 files; lowest per-file lines `error-service.ts` at 78.94%.
  - [x] 3.2 N/A — all four metrics ≥70% AND no per-file <50%; recorded figures.
  - [x] 3.3 N/A — no spec files added.
  - [x] 3.4 N/A — `*.types.ts` files do not appear in the v8 matrix (no emitted JS); no Vitest `coverage.exclude` needed.
  - [x] 3.5 N/A — `app.ts` / `app.routes.ts` / `app.config.ts` already covered (the SPA's `app.spec.ts` spec exercises bootstrap); no exclusion needed.

- [x] **Task 4 — E2E spec-count attestation (AC7)**
  - [x] 4.1 `ls e2e/tests/` confirmed six `*.spec.ts` files matching the AC7 list (j1, j2, j3, j4, j5, j6).
  - [x] 4.2 `cd e2e && npx playwright test --list` reports `Total: 26 tests in 6 files`.
  - [x] 4.3 `e2e/playwright.config.ts:15` still pins `workers: 1` (verified by grep).
  - [x] 4.4 Live run (inlined Justfile recipe because `just` is not on the audit host's PATH; mirrors Story 4.4 dev-time approach): `docker compose -f docker-compose.yml -f compose/app.e2e.yml --profile e2e` up + run --build playwright. **26 passed (53.0s).** Cleanup via `trap … EXIT` succeeded.

- [x] **Task 5 — Author `docs/coverage-report.md` (AC2)**
  - [x] 5.1 Created `docs/coverage-report.md` (`docs/` directory was empty before this story).
  - [x] 5.2 All required sections present: header (date + SHA + status), Reproduce block, Targets table, per-surface sections (BFF / RS / SPA / E2E), Method section, Gaps-closed section, plus an informational "Notes on per-file gaps" tail.
  - [x] 5.3 Numbers quoted verbatim from the live runs in Tasks 1–4; no rounding beyond two decimals.
  - [x] 5.4 "Gaps closed in this run" section explicitly records "None" — no tests added.

- [x] **Task 6 — Add README reference (AC8)**
  - [x] 6.1 Added single line under the existing "Architecture overview" section (after the `architecture.md` link).
  - [x] 6.2 No other README changes.

- [x] **Task 7 — Regression sweep (DoD)**
  - [x] 7.1 BFF `pytest --cov` (Task 1.1) reported `543 passed, 109 warnings in 10.15s` — matches Story 4.4 baseline exactly; the coverage run IS the regression run.
  - [x] 7.2 RS `pytest --cov` (Task 2.1) reported `324 passed, 1 warning in 8.34s` — matches Story 4.4 baseline exactly.
  - [x] 7.3 SPA `npm test -- --coverage` (Task 3.1) reported `Test Files 19 passed (19) | Tests 152 passed (152)` — matches Story 4.4 baseline exactly.
  - [x] 7.4 `cd spa && npm run build` exits 0; bundle generation complete (`main-GU7GPXNO.js` 5.55 kB initial + lazy chunks for book-list-page / settings-page / login-view as expected).
  - [x] 7.5 N/A — no new BFF test files.
  - [x] 7.6 N/A — no new RS test files.

- [x] **Task 8 — Capture deferred items (DoD)**
  - [x] 8.1 No new deferred items surfaced. Every surface met threshold first run with substantial headroom (BFF +7.26pp, RS +8.33pp, SPA +21–25pp on each of the four metrics, E2E 6 specs vs 5 floor). The informational "Notes on per-file gaps" section in `docs/coverage-report.md` lists the natural follow-up polish items but they are NOT deferred — they remain in-scope-but-unprioritized for any future test-quality pass.

## Files this story creates / modifies

**Created:**
- `docs/coverage-report.md` — the single source-of-truth coverage snapshot (Task 5).

**Modified (always):**
- `README.md` — one reference line to `docs/coverage-report.md` (Task 6).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `5-1-...` status transitions `ready-for-dev` → `in-progress` → `review` → (after code review) `done`; `epic-5` transitions `backlog` → `in-progress` (this is the first Epic 5 story, so the workflow makes the transition automatically).
- `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md` (this file) — Tasks/Subtasks checkboxes marked; Dev Agent Record filled; Change Log entries added.
- `_bmad-output/implementation-artifacts/deferred-work.md` — appended "Deferred from: dev of 5-1-..." section IF Task 8 surfaces items.

**Modified (conditionally — only if a gap exists or an exclusion is needed):**
- `services/bff/pyproject.toml` — `[tool.coverage.run] omit` entries with comment justification (Task 1.4).
- `services/resource-server/pyproject.toml` — `[tool.coverage.run] omit` entries (additions to the existing block, Task 2.3).
- `spa/vitest.config.ts` (or wherever Vitest resolves config from — likely `vitest.config.ts` at SPA root, but Angular 21 may proxy through `angular.json`; verify) — `coverage.exclude` globs (Task 3.4 / 3.5).
- `services/bff/tests/<mirror>/test_<name>.py` — net-new BFF test files for gap-fill (Task 1.3).
- `services/resource-server/tests/<mirror>/test_<name>.py` — net-new RS test files (Task 2.2).
- `spa/src/app/<feature>/<name>.spec.ts` — net-new SPA spec files (Task 3.3).

**Files this story explicitly does NOT touch:**
- `services/bff/src/**` / `services/resource-server/src/**` / `spa/src/app/**` (source code) — this is a test-and-report story. No production code changes. If a coverage gap reveals a bug, log it as a defer item; do not fix it here.
- `e2e/**` — Story 4.4 closed Epic 4 E2E with all 26 tests green. The audit is read-only on E2E.
- `compose/**`, `docker-compose.yml`, `Justfile`, `keycloak/**` — no infra changes.
- `_bmad-output/planning-artifacts/**` — planning docs are frozen.
- `services/resource-server/CLAUDE.md` — RS agent rules; read-only context.

## Failure-prevention checklist

1. **Do NOT lower a threshold to make the report pass.** `fail_under = 90` on the BFF and RS, and the ≥70% / ≥50% rules on the SPA, are NFR11-locked. If the audit reveals real gaps, fill them; do not tune them away.
2. **Do NOT touch production source.** This story is tests + report + README reference. A coverage gap that requires a source change is a defect — defer it (Task 8.1) and report that surface as `Status: All thresholds met with deferred defect: D<NNN>`.
3. **Do NOT invent new test paths.** Backend tests mirror `src/<svc>/` (architecture line 615); SPA tests colocate (architecture line 576). The anti-pattern of "a backend test under `tests/utils/` for code that lives in `src/<svc>/services/`" is explicitly called out at architecture line 858.
4. **Do NOT add a Python `omit` without a comment block.** RS's pattern (lines 82-99) is the canonical shape — one paragraph naming the module + reason + the story that introduced it.
5. **Do NOT add a Vitest `coverage.exclude` without inline justification.** Use the same comment-block discipline so the next maintainer can read the config and understand why each entry is there.
6. **Do NOT rewrite the README.** AC8 is one line of text. Story 5.3 owns the full README.
7. **Do NOT skip the live E2E run.** Spec-count is necessary but not sufficient for AC7 — the live `just e2e-up` (or compose form) must exit 0 with the full 26-test pass. Story 4.4 retro P2 codified this rule.
8. **Do NOT modify the existing RS `omit` list** (lines 100-109). Those seven entries are documented archetype carve-outs from Story 3.1 — touching them changes RS coverage history. New omissions are appended, not edited.
9. **Do NOT report `Status: All thresholds met` if any aggregate is below threshold.** Even if all per-file scores pass, an aggregate fail means a fail. The status line is load-bearing for the project's final attestation.
10. **Do NOT trust prior story DARs as the current figure.** Re-run; record what comes out now. The "97.26% BFF" / "88.23%/78.57% estimate-cell" numbers from 4.2 / 4.3 DARs are point-in-time captures; the only authoritative figure for this audit is what comes out of the live commands run for this story.
11. **Do NOT commit HTML coverage artifacts.** `htmlcov/`, `coverage/`, and similar directories should be gitignored already (verify before committing); if any leak, do not stage them.
12. **Do NOT touch Story 4.4's modifications to `Justfile` or `e2e/README.md`** (the "Compose-runner gotcha" subsection). They are Story 4.4 deliverables; this story consumes them unchanged.

## Dev Notes

### Architecture and code constraints relevant to this story

- **Coverage targets are NFR11.** PRD line establishing the rule cited in the epic AC at lines 1752 / 1775 / 1780 / 1785. Architecture restates them at lines 46 + 272 + 1415. The pyproject.toml `fail_under = 90` on both BFF and RS is the **archetype's** threshold, which is one tick stricter than the PRD's >70% floor.
- **Source layout for new tests.**
  - BFF: `services/bff/tests/<api|services|auth|core|aop>/test_<name>.py`. Existing BFF test count is 543 (story 4.4 DAR).
  - RS: `services/resource-server/tests/<api|services|auth|core|aop>/test_<name>.py`. Existing RS test count is 324.
  - SPA: `spa/src/app/<feature>/<name>.spec.ts` colocated. Existing test count is 152 across 19 files.
- **`pyproject.toml` coverage config — current state:**
  - **BFF (`services/bff/pyproject.toml:82-87`):**
    ```toml
    [tool.coverage.run]
    source = ["src"]

    [tool.coverage.report]
    fail_under = 90
    show_missing = true
    ```
    No `omit` entries today. The BFF has never needed one because nothing in its `src/` is dead.
  - **RS (`services/resource-server/pyproject.toml:80-113`):** carries a seven-entry `omit` list from Story 3.1 (archetype-emitted modules that are kept on disk but never invoked from `main.py`). The comment block at lines 82-99 is the canonical justification pattern.
- **SPA Vitest config location:** `spa/vitest.config.ts` is the expected location. If it doesn't exist (Angular 21 + Vitest is a fresh combination — confirm at run time), Vitest configuration may live inside `angular.json` under the test builder options. Touch whichever file Vitest actually reads when `npm test -- --coverage` runs. The dev should `grep -r "coverage" spa/*.json spa/*.ts` first to find the active config.
- **README placement:** the README is currently a 28-line stub (per ls before this story). Story 5.3 will rewrite it. AC8 here is one line, ideally appended to the "Architecture overview" section's existing paragraph (after the `architecture.md` link) so the rewrite has minimum churn to integrate.

### Source-of-truth references for current coverage state (do NOT cite as the audit's answer)

- Story 4.2 DAR (`_bmad-output/implementation-artifacts/4-2-...md` Change Log v2.0 / sprint-status.yaml comment line 39): "BFF tests passing (+2 new empty-body coverage), coverage 97.26%; rsc.py at 100%". As of `b905307`. Stories 4.3 + 4.4 touched no BFF source.
- Story 4.3 DAR (`4-3-...md` Change Log v2.0): "SPA suite 152/152 green, coverage 88.23%/78.57% on estimate-cell.ts and 100%/85% on books-service.ts". This is **per-file**, not aggregate. The aggregate SPA figure has never been published.
- Story 4.4 DAR (`4-4-...md` Change Log v1.0 + sprint-status.yaml line 39): "BFF 543/RS 324/SPA 152 unit tests green; SPA build green; SPA lint has 3 pre-existing `no-fallthrough` errors (D127)". Test counts only; no coverage figures.
- RS coverage history: no aggregate figure recorded across Stories 3.1–4.1.

### Previous-story intelligence

- **From Story 4.4 (the immediate predecessor):**
  - 26 E2E tests in 6 spec files is the load-bearing AC7 target. The breakdown J1×3 / J2×8 / J3×5 / J4×5 / J5×2 / J6×3 is what the live run must report.
  - `just e2e-up` is the canonical command (NOT `npx playwright test` directly), per Story 3.6 + Story 4.4 retro P2 chain. AC7 of this story inherits that rule.
  - `Justfile`'s `e2e-up` now passes `--build` (story 4.4 Change Log v1.1) — this means a fresh image is built every run. Cold-cache build was unmeasured (D130); for the audit's live run, budget time accordingly.
  - SPA pre-existing lint errors (D127) are out of scope here; do not "fix on the way" because lint and coverage are orthogonal.
- **From Story 4.2 (BFF coverage was 97.26%):** the BFF added 543 tests including 21 new tests for `compute_estimate` + 22 for the POST `/v1/books/{id}/estimate` handler. The `services/bff/src/bff/services/resource_server_client.py` module was at 100% per-file coverage. Net effect: the BFF should pass AC5 without further work unless an audit reveals an unrelated regression.
- **From Story 3.1 (RS scaffold):** the `omit` list at `services/resource-server/pyproject.toml:100-109` excludes seven archetype-emitted modules. The Story 3.1 dev log (cited in the comment block lines 82-99) is the authority on why each is excluded. This story preserves the list verbatim and only **appends** to it.

### Git intelligence (recent commits relevant to coverage)

- `3e3612a feat(4.4): E2E specs — J3 estimate + J6 RS unavailable` ← baseline for this story; 26 E2E tests live, no source / no compose touched.
- `bb15aca Merge story 4.3 — SPA EstimateCell real component + BooksService.requestEstimate` ← last SPA source touch.
- `b905307 chore(4.2): code review — P1-P7 applied, mark done, log D119-D126` ← last BFF coverage delta (97.26% aggregate).
- `05b8de7 chore(4.3): code review — P1 applied, mark done` ← SPA tests at 152.
- `3513e66 feat(4.3): SPA EstimateCell real component + BooksService.requestEstimate` ← last SPA spec touch.
- `e3236bd feat(4.2): BFF POST /v1/books/{id}/estimate + ResourceServerClient.compute_estimate` ← BFF reached 543 tests.
- `19cb3f8 feat(4.1): RS POST /v1/estimate + estimate_service + format_duration helper` ← RS reached 324 tests.

Implication: the BFF and RS aggregates should already be in compliance because every endpoint has been test-driven across Epics 1–4. The SPA is the most likely surface to need backfill, primarily because nothing in any prior story has audited the aggregate.

### Testing standards

- **Backend (pytest + pytest-cov):**
  - Use the same `addopts = "--strict-markers -ra"` config the services already declare (BFF line 79 / RS line 77).
  - New tests use the canonical `def test_<scenario>(<fixtures>): ...` shape; async tests use `asyncio_mode = "auto"` which is already enabled in both pyprojects.
  - Coverage-only test files (i.e., tests added solely to bump a line) should still pin a real behavior — never write `assert True` filler. The convention is `test_<module>_<line_or_behavior>__<assertion>`.
  - Use the `term-missing` output to pinpoint exact line numbers that need exercise. Then write a test that exercises that branch with a meaningful assertion (most often the test ends up valuable beyond the coverage push).
- **SPA (Vitest + Angular TestBed):**
  - Component tests use `TestBed.configureTestingModule({ ... })` with the component declared; the existing pattern across `estimate-cell.spec.ts`, `book-row.spec.ts`, etc. is the canonical shape.
  - For pure-function modules (e.g., `auth.types.ts` parsers, error-service.ts mappers), prefer plain `describe / it / expect` without TestBed.
  - Coverage-only spec files use the same `<name>.spec.ts` filename pattern; no special suffix.

### Latest tech information

- **pytest-cov ≥6.0** (resolved by both pyprojects). The `--cov-report=html` flag emits `htmlcov/index.html` by default; the `--cov-report=term-missing` flag is what the gap report quotes when listing per-file gaps.
- **Vitest 4.x + `@vitest/coverage-v8` 4.1.6** (per `spa/package.json`). V8 coverage in Vitest 4 reports statements / branches / functions / lines as four separate metrics by default. Aggregate is per-metric; per-file table is per-metric. Excludes are globs in `vitest.config.ts` under `test.coverage.exclude` (Vitest 4 location).
- **Playwright 1.49.x** (Story 1.11 install): `npx playwright test --list` exit code 0 + the `Total: N tests in M files` footer is the spec-count assertion machine.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Epic 5` lines 1744–1746] (epic overview)
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.1` lines 1748–1798] (verbatim AC source)
- [Source: `_bmad-output/planning-artifacts/epics.md#NFR11` line 38] (≥70% SPA / >90% backend / ≥5 E2E)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Project Context Analysis` lines 46–48] (test-coverage + security-posture)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Locked by user mandate — backend archetype` line 77] (pytest + coverage target >90%)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Testing Framework` line 272] (SPA coverage ≥70% via Vitest)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Backend services (archetype layout, preserved)` lines 595–610] (where backend tests live; mirror rule line 615)
- [Source: `_bmad-output/planning-artifacts/architecture.md#TypeScript / Angular code (SPA)` line 576] (SPA `<name>.spec.ts` colocation rule)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Process Patterns / Tests` line 858] (anti-pattern: backend test under `tests/utils/`)
- [Source: `_bmad-output/planning-artifacts/architecture.md#Requirements Coverage Validation` lines 1398–1415] (full NFR11 cross-walk)
- [Source: `services/bff/pyproject.toml` lines 76–87] (BFF pytest + coverage config — `fail_under = 90`)
- [Source: `services/resource-server/pyproject.toml` lines 73–113] (RS pytest + coverage config — `fail_under = 90` + omit block)
- [Source: `spa/package.json` lines 4–12 + 31] (SPA `test` script + `test:coverage` alias + `@vitest/coverage-v8` dependency)
- [Source: `services/resource-server/CLAUDE.md`] (RS agent rules — ruff / ty / pytest must all pass before commit)
- [Source: `_bmad-output/implementation-artifacts/4-4-e2e-specs-j3-estimate-j6-rs-unavailable.md` Change Log v1.0–v2.0] (E2E 26-test green; SPA lint D127 carry-out)
- [Source: `_bmad-output/implementation-artifacts/sprint-status.yaml` lines 86–99] (epic 4 = in-progress with 4.4 review→done; epic 5 stories = backlog)
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md#D113`–`#D135`] (Epic-4-era deferred items; D127 SPA lint is most likely to overlap with anything surfaced here, but it is OUT of scope)
- [Source: `README.md` lines 22–24] (existing "Architecture overview" section — natural insertion point for AC8 reference)
- [Pattern: `services/resource-server/pyproject.toml` lines 82–99] (canonical `omit` comment-block pattern; replicate in BFF if a new omission is added)
- [Pattern: `e2e/playwright.config.ts:14`] (`workers: 1` invariant — AC7 verification)
- [Pattern: `Justfile e2e-up`] (canonical E2E live-run command; Story 4.4 Change Log v1.1 added `--build`)

## Definition of Done

1. `docs/coverage-report.md` exists with all six sections from AC2 (header, Reproduce, Targets, BFF, RS, SPA, E2E, Method, Gaps closed).
2. The report's "Status" line reads `All thresholds met` OR `All thresholds met with documented exclusions` (per AC9); never `Below threshold` and never absent.
3. The report cites the **commit SHA the run was made against** (`git rev-parse HEAD`) and the **run date** in ISO-8601 form.
4. `cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing` exits 0 with aggregate ≥90% and no per-file <70%. Numbers transcribed verbatim to the report.
5. `cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing` exits 0 with aggregate ≥90% and no per-file <70%. Numbers transcribed verbatim.
6. `cd spa && npm test -- --coverage` exits 0 with aggregate ≥70% on each of statements / branches / functions / lines, and no per-file <50% on lines. Numbers transcribed verbatim.
7. `ls e2e/tests/` shows exactly the six spec files listed in AC7; `cd e2e && npx playwright test --list` reports `Total: 26 tests in 6 files`.
8. Live `just e2e-up` (or compose equivalent) exits 0 with all 26 tests green. The runner's footer string is captured in the report's E2E section.
9. `README.md` contains a single reference line to `docs/coverage-report.md` placed per AC8.
10. Any new BFF / RS test files satisfy `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, and the relevant pytest suite, in the relevant service directory. (RS CLAUDE.md is non-negotiable on this.)
11. Any new SPA spec files satisfy `npm test -- --watch=false` and do not regress `npm run build`. (`npm run lint` is allowed to surface the pre-existing D127 errors — those are out of scope.)
12. Any deliberate exclusions added to a `pyproject.toml omit` or Vitest `coverage.exclude` include an inline justification comment block AND appear in the report's per-surface "Excluded" subsection.
13. `_bmad-output/implementation-artifacts/sprint-status.yaml` reflects `5-1-coverage-audit-gap-fill: ready-for-dev → in-progress → review` with `epic-5: backlog → in-progress` (the latter handled automatically by the create-story workflow on this same run).
14. Any items surfaced during dev / code review that are not actioned here are logged in `_bmad-output/implementation-artifacts/deferred-work.md` under a new "Deferred from: dev of 5-1-..." section with severity / "Belongs to" tags. Numbering starts at D136.

### Review Findings

- [x] [Review][Patch] DN1 (→ patch) — Softened `fail_under = 90` framing: updated AC5 to "≥90% line coverage" with explicit `precision = 0` semantics; Targets table in `docs/coverage-report.md` now cites "≥90% line ... effective floor ~89.5% rounded". No config change.
- [x] [Review][Patch] P1 — SPA HTML path mis-stated: report said `spa/coverage/index.html` but Angular builder writes to `spa/coverage/spa/index.html`. Patched `docs/coverage-report.md:22`.
- [x] [Review][Patch] P2 — `estimate-cell.ts` missing-line list inconsistent (SPA section: `86, 129, 142-143`; Notes section: `86 and 142-143`). Reconciled — Notes section now also lists line 129.
- [x] [Review][Patch] P3 — `error-service.ts` "5 lines missing — 82-96" mixed a count with a 15-line range. Rewritten to list the uncovered `case` branches explicitly without claiming a specific statement count that couldn't be reconciled with the cited line range.
- [x] [Review][Patch] P4 — Inlined E2E reproduce recipe replaced with `bash -c 'set -e; trap "..." EXIT; ...'` to match the Justfile's tear-down semantics on Ctrl-C / failure paths.
- [x] [Review][Patch] P5 — DAR Task 3.5 typo `spec-app-app.js` → `app.spec.ts` (verified: `spa/src/app/app.spec.ts` exists).

**Dismissed as noise (8):** "four per-file gaps" vs five files (four bullets in Notes match sprint-status comment); estimate-cell.ts "regression" 88.23%→86.66% (cross-metric comparison — different metrics, not a regression); AC1 HTML-index assertion missing from DAR (HTML files verified on disk); E2E exit code never quoted (`26 passed` line is sufficient evidence); SPA `**/*.types.ts` exclude framing (spec hedged correctly, report categorical because empirically verified); BFF `1421/1461` format nit; README placement implied from diff (placement verified correct on disk); pytest-cov exit-code attestation not quoted in DAR.

#### Second-pass review (after first-pass patches applied)

- [x] [Review][Patch] P6 — `invalid_input` double-listed in `error-service.ts` bullet (introduced by P3 rewrite). Reconciled: dropped `invalid_input` from the "covered" tail; report now matches the original Notes-section claim of three cases the SPA relies on (`session_expired`, `reading_speed_unset`, `resource_server_unavailable`). [`docs/coverage-report.md:63`]
- [x] [Review][Patch] P7 — `sprint-status.yaml:95` `review` → `done`. (The first attempt was clobbered by a parallel turn that touched the same file; re-applied.)
- [x] [Review][Patch] P8 — DN1 softening propagated uniformly: AC5 heading (171), AC6 heading + Given + Then (182, 184, 186), AC2 template Targets rows (98-99), Task 1.2 path (241), DoD #4/#5 (426-427), and Completion Notes lines (521-522) now all say "≥90%" with `precision = 0` clarification where appropriate.
- [x] [Review][Patch] P9 — AC1 SPA HTML path updated to `spa/coverage/spa/index.html` (Angular's `@angular/build:unit-test` builder wraps Vitest); aligns AC1 spec wording with the P1-patched report and on-disk reality.

**Dismissed second-pass noise (~7):** estimate-cell cross-metric (first-pass dismissal stands); 5+2 patch-count framing (DN1 touched two locations); Targets-table "Source" column format nits; AC8 reference-snippet backticks; "Other per-file <95%" omits the 84% file (deliberate split); Reproduce-block per-line cwd convention; `auth/factory.py` line-vs-statement ambiguity (coverage.py multi-line statement quirk).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context).

### Debug Log References

**BFF (Task 1.1):**
```
$ cd services/bff && uv run pytest --cov=src/bff --cov-report=term-missing --cov-report=html
... 543 passed, 109 warnings in 10.15s
TOTAL  1461  40  97%   (97.26%)
Required test coverage of 90.0% reached. Total coverage: 97.26%
```
Per-file lowest: `core/database.py` 84% (lines 27-29, 48, 53-55, 79). All ≥70%.

**RS (Task 2.1):**
```
$ cd services/resource-server && uv run pytest --cov=src/resource_server --cov-report=term-missing --cov-report=html
... 324 passed, 1 warning in 8.34s
TOTAL  840  14  98%   (98.33%)
Required test coverage of 90.0% reached. Total coverage: 98.33%
```
Per-file lowest: `auth/factory.py` 77% (lines 30, 38-45, 55). All ≥70%.

**SPA (Task 3.1):**
```
$ cd spa && npm test -- --coverage
Test Files 19 passed (19)
Tests 152 passed (152)
Coverage summary:
  Statements   : 94.71% ( 699/738 )
  Branches     : 91.16% ( 382/419 )
  Functions    : 95.74% ( 90/94 )
  Lines        : 94.52% ( 535/566 )
```
Per-file lowest lines: `app/shared/errors/error-service.ts` 78.94%. All ≥50% hard floor.

**E2E static (Task 4.1, 4.2, 4.3):**
```
$ ls e2e/tests/
j1-first-login.spec.ts  j2-manage-books.spec.ts  j3-estimate.spec.ts
j4-adjust-speed.spec.ts  j5-logout.spec.ts        j6-rs-unavailable.spec.ts
$ cd e2e && npx playwright test --list
Total: 26 tests in 6 files
$ grep -n "workers" e2e/playwright.config.ts
15:  workers: 1,
```

**E2E live (Task 4.4):**
```
$ cd /Users/fralo/nearform/AINE_Training/BMAD_books && bash -c '<inlined Justfile e2e-up>'
... Image bmad_books-playwright Built ... Container keycloak/bff/resource-server Healthy
Running 26 tests using 1 worker
  ✓ 1-26 (all green; J1×3 J2×8 J3×5 J4×5 J5×2 J6×3)
  26 passed (53.0s)
Container teardown: keycloak/bff/resource-server stopped + removed; network removed.
```

**SPA build regression (Task 7.4):**
```
$ cd spa && npm run build
Application bundle generation complete. [0.893 seconds]
Initial total: 255.77 kB / 71.97 kB transfer
Lazy chunks: book-list-page 57.81 kB, settings-page 5.45 kB, login-view 2.10 kB
```

### Completion Notes List

- **Pure attestation pass — zero source / test / config changes.** Every threshold was already met at baseline `3e3612a`. The story produced the audit document (`docs/coverage-report.md`) and a single README reference line; nothing else moved.
- **All NFR11 thresholds substantially exceeded:**
  - BFF: 97.26% line vs ≥90% target (+7.26pp); lowest per-file `core/database.py` 84% vs ≥70% floor (+14pp).
  - RS: 98.33% line vs ≥90% target (+8.33pp); lowest per-file `auth/factory.py` 77% vs ≥70% floor (+7pp).
  - SPA: 94.71% / 91.16% / 95.74% / 94.52% (statements / branches / functions / lines) vs ≥70% target across all four metrics (+21pp to +25pp); lowest per-file lines `error-service.ts` 78.94% vs ≥50% hard floor (+29pp).
  - E2E: 6 specs / 26 tests covering J1–J6 vs ≥5 floor; live `e2e-up` 26/26 green in 53.0s.
- **No `omit` / `coverage.exclude` additions.** RS's seven-entry `omit` block (Story 3.1) preserved verbatim. BFF's empty `omit` block unchanged. SPA's Angular-builder-managed Vitest defaults left intact (no `vitest.config.ts` exists at SPA root — coverage is collected through `@angular/build:unit-test` with default include/exclude; `*.types.ts` files emit no JS and don't appear in the matrix).
- **No deferred items logged.** All findings landed comfortably above thresholds; the four per-file gaps surfaced in the report (`core/database.py`, `auth/factory.py`, `error-service.ts`, `estimate-cell.ts`) are documented as informational follow-ups (lifecycle paths, archetype Azure-AD branch, defensive error envelope shapes, signal-invariant guards), NOT as deferred work. They do not regress any threshold.
- **Operational note about `just e2e-up`:** the audit host has no `just` binary (same as Story 4.4 dev). The Justfile recipe was inlined verbatim into a `bash -c '...'` block. Story 4.4's `--build` flag on `docker compose run` was load-bearing here too — without it the cached runner image would have run an older spec set.
- **README reference placement:** added as a single line after the existing `architecture.md` link inside the "Architecture overview" section. Story 5.3 owns the full README rewrite; this story's edit is one line so 5.3's rewrite has minimum churn to absorb.
- **Pre-existing SPA lint failures (D127):** out of scope for this story per Failure-prevention checklist item 1. Not touched.

### File List

**Created (Task 5):**
- `docs/coverage-report.md` — the per-surface coverage snapshot.

**Modified (Task 6):**
- `README.md` — single line under "Architecture overview" referencing `docs/coverage-report.md`.

**Modified (workflow-managed):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `5-1-coverage-audit-gap-fill` status transitions `ready-for-dev` → `in-progress` → `review`; `epic-5` already at `in-progress` from the create-story turn; `last_updated` extended with dev-pass summary.
- `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md` (this file) — Tasks/Subtasks checkboxes marked; Dev Agent Record filled; Change Log v1.0 entry added; Status `ready-for-dev` → `review`.

**Explicitly NOT modified** (verified via `git status` after dev): `services/bff/src/**`, `services/bff/tests/**`, `services/bff/pyproject.toml`, `services/resource-server/src/**`, `services/resource-server/tests/**`, `services/resource-server/pyproject.toml`, `spa/src/**`, `spa/package.json`, `spa/angular.json`, `e2e/**`, `compose/**`, `docker-compose.yml`, `Justfile`, `keycloak/**`, `_bmad/**`, `_bmad-output/planning-artifacts/**`.

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-18 | 0.1 | Story file created. Baseline commit `3e3612a` (Story 4.4 merge to `main`). Epic 5 = in-progress (transitioned from `backlog` by this story's create-story run). All Epic 1–4 prerequisites done; 26 E2E tests live; BFF coverage last measured 97.26% at `b905307`; RS aggregate not previously measured; SPA aggregate not previously measured. NFR11 is the load-bearing target. | claude-opus-4-7 |
| 2026-05-18 | 1.0 | Dev pass complete; status `ready-for-dev` → `review`. Pure attestation — zero source / test / config changes. Captured fresh numbers from all three coverage commands + live `e2e-up`: BFF 97.26% (543 tests), RS 98.33% (324 tests), SPA 94.71%/91.16%/95.74%/94.52% (152 tests across 19 files), E2E 26/26 green in 53.0s. All thresholds substantially exceeded. Created `docs/coverage-report.md`; added single-line reference in `README.md` under "Architecture overview". No `omit` / `coverage.exclude` changes. No deferred items logged — the four per-file gaps surfaced (`core/database.py` 84%, `auth/factory.py` 77%, `error-service.ts` 78.94%, `estimate-cell.ts` 86.66%) are documented as informational follow-ups, all above per-file floors. Operational note: `just` binary not on audit host so the Justfile recipe was inlined into bash (same approach as Story 4.4 dev). | claude-opus-4-7 |
| 2026-05-18 | 1.1 | Code review pass → done. bmad-code-review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) ran in parallel. 6 patches applied (1 was DN1 reclassified after user input): DN1 softened `fail_under = 90` framing — updated AC5 to ≥90% with explicit `precision = 0` semantics + Targets-table source citation now reads "effective floor ~89.5% rounded"; P1 SPA HTML path corrected `spa/coverage/index.html` → `spa/coverage/spa/index.html` (Angular builder nests one directory deeper); P2 `estimate-cell.ts` missing-line list reconciled (line 129 was dropped from the Notes section); P3 `error-service.ts` count-vs-range conflict resolved by listing uncovered `case` branches explicitly; P4 inlined E2E reproduce recipe rewritten as `bash -c 'set -e; trap "..." EXIT; ...'` to match Justfile cleanup semantics; P5 DAR typo `spec-app-app.js` → `app.spec.ts`. 8 findings dismissed as noise (four-vs-five gap count, cross-metric estimate-cell "regression", HTML-index DAR attestation, E2E exit-code quote, types.ts exclude framing, BFF format nit, README placement, pytest-cov exit-code quote). No defers logged — every patch was a doc-accuracy fix landing in `docs/coverage-report.md` (5) or this story file's DAR/AC5 (2). Acceptance Auditor returned PASS on all 9 ACs + 12 failure-prevention items + 14 DoD items pre-patch; post-patch the same surface holds (no behavior changed — only report wording + spec wording). | claude-opus-4-7 |
| 2026-05-18 | 1.2 | Second-pass code review at user request. Same three layers re-ran on the patched diff and surfaced 4 real follow-on findings — all doc-only, none behavioral: **P6** the P3 rewrite for `error-service.ts` accidentally listed `invalid_input` in BOTH the "not yet exercised" list and the "covered" list of the same bullet; reconciled by dropping it from the covered list (only three cases the SPA currently relies on: `session_expired`, `reading_speed_unset`, `resource_server_unavailable`). **P7** the prior `sprint-status.yaml` structured-field edit (`5-1: review → done`) was clobbered by a concurrent turn that touched the same file (5.2 context-creation); re-applied. **P8** the DN1 softening was incomplete on the first pass — AC5 body got "≥90%" but AC5 heading, AC6 (heading + Given + Then), AC2 template, Task 1.2, DoD #4/#5, and Completion Notes still said ">90%"; propagated the softening uniformly with `precision = 0` clarification. **P9** AC1 line 65 still cited `spa/coverage/index.html (Vitest default)` even though P1 had updated the report to `spa/coverage/spa/index.html`; aligned AC1 wording to the same Angular-builder-wraps-Vitest semantics. ~7 noise findings dismissed (cross-metric estimate-cell again, patch-count framing 5+2, Targets source column format, AC8 backticks, "Other below 95%" omission of the 84% file, Reproduce-block cwd convention, auth/factory.py multi-line-statement coverage.py quirk). No behavior changed across either pass — every patch landed in `docs/coverage-report.md` or this story file's AC/Task/DoD wording. All four NFR11 thresholds still substantially exceeded. | claude-opus-4-7 |
