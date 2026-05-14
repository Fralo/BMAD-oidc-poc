---
status: done
baseline_commit: 215d84e78cf3b3b98afdad6abb62e2d39c1d5ff9
story_key: 1-1-repo-scaffold-compose-skeleton
specLoopIteration: 1
---

# Story 1.1: Repo scaffold + compose skeleton

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer onboarding to the project,
I want a working monorepo skeleton with `docker compose config` validating cleanly,
so that I can extend each part (services, SPA, compose includes) without first inventing the structure.

## Acceptance Criteria

1. **Top-level files exist at the repo root:** `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`, `README.md`, `CLAUDE.md`. (`CLAUDE.md` already exists with the project-conventions stub; do **not** overwrite — leave its existing content intact and append only if explicitly required.)
2. **Top-level directories exist** (as empty placeholders unless otherwise noted): `spa/`, `services/bff/`, `services/resource-server/`, `keycloak/`, `e2e/`, `compose/`. `tools/` is created locally but listed in `.gitignore` (it will hold the cloned archetype in later stories).
3. **`compose/infra.yml` and `compose/app.yml` exist as compose-include scaffolds.** They are valid Compose YAML files with `services: {}` placeholders (or commented-out service stubs); no app services are defined yet — those land in later Epic 1 stories.
4. **`docker-compose.yml` uses Compose's `include:` directive** (Compose v2.20+) to pull in both `compose/infra.yml` and `compose/app.yml`, and it declares three profiles consistent with AR26: `default`, `dev`, `e2e`. (Profile declarations may be a top-level `profiles:` block listing the names, or per-service `profiles:` once services exist — for this scaffold story, the file must at minimum declare the three names so later stories can attach services to them.)
5. **`.env.example` documents every required env var from AR29 with placeholder/example values:** `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `BFF_DATABASE_URL`, `RS_DATABASE_URL`, `BFF_BASE_URL`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `BFF_SESSION_COOKIE_NAME`, `BFF_CSRF_COOKIE_NAME`, `BFF_SESSION_COOKIE_SECURE`, `ENABLE_TEST_RESET`, `TEST_RESET_TOKEN`. Each var has either a placeholder (e.g., `BFF_CLIENT_SECRET=change-me`) or a working example (e.g., `BFF_DATABASE_URL=sqlite+aiosqlite:////data/bff.db`). No real secrets.
6. **`.gitignore` lists `tools/fastapi-archetype/`** (and standard ignores: per-service `.env` files, Python `__pycache__/`, `node_modules/`, `dist/`, `.coverage`, `.pytest_cache/`, `.uv/`, `*.sqlite*`, OS junk like `.DS_Store`).
7. **`.dockerignore` exists** with at least: `.git`, `.gitignore`, `_bmad/`, `_bmad-output/`, `tools/`, `**/node_modules`, `**/__pycache__`, `**/*.pyc`, `**/.env`, `**/dist`, `**/.pytest_cache`.
8. **`docker compose config` validates cleanly** from the repo root with no errors and no warnings beyond the standard "no services defined" notes (empty stack is acceptable at this story; later stories add services).
9. **README.md** contains: (a) project name and one-paragraph description, (b) setup instructions — clone the repo, clone the archetype into `tools/fastapi-archetype/` (the exact command lives in later stories; for now a placeholder pointing to AR1 is acceptable), copy `.env.example` to `.env`, run `docker compose up`, (c) a "## Architecture overview" stub section pointing readers to `_bmad-output/planning-artifacts/architecture.md`, (d) a "## AI integration log" stub section to be filled in by Story 5.3.

## Tasks / Subtasks

- [x] **Task 1 — Create top-level directories** (AC: #2)
  - [x] Create `spa/`, `services/bff/`, `services/resource-server/`, `keycloak/`, `e2e/`, `compose/`, `tools/` at the repo root. Use `.gitkeep` files (single empty file inside each empty directory) so Git tracks them.
- [x] **Task 2 — Author `.gitignore` and `.dockerignore`** (AC: #6, #7)
  - [x] Write `.gitignore` covering `tools/fastapi-archetype/`, per-service `.env`, Python/Node/Angular/test-tool artifacts, OS files, SQLite DB files.
  - [x] Write `.dockerignore` covering `.git`, `_bmad/`, `_bmad-output/`, `tools/`, Node/Python caches, `dist/`, `.env*`.
- [x] **Task 3 — Author `.env.example`** (AC: #5)
  - [x] List every AR29 env var with a placeholder or working example. Group with comment headers (Keycloak, BFF, RS, OIDC, cookies, test-reset).
  - [x] Confirm no real secrets are present; use literal placeholder strings like `change-me` or `<your-...>`.
- [x] **Task 4 — Author `compose/infra.yml` and `compose/app.yml` scaffolds** (AC: #3)
  - [x] Each file: valid Compose YAML; specify a Compose `name:` or rely on the top-level project name; include `services: {}` (or a commented stub) so the file is parseable. Do **not** declare any services yet.
- [x] **Task 5 — Author top-level `docker-compose.yml`** (AC: #4)
  - [x] Use `include:` pointing to both `compose/infra.yml` and `compose/app.yml`.
  - [x] Declare the three profile names — `default`, `dev`, `e2e` — in a way that survives `docker compose config`. Pragmatic approach: add a top-level `x-profiles: [default, dev, e2e]` extension field as a self-documenting placeholder, **or** add an inert `services:` block that references the profiles, **or** declare them via the first service added later. For this story the minimum is that the three profile names appear in the file in a form a later reader can recognize as intent. The verification AC is the `docker compose config` validation in Task 7.
- [x] **Task 6 — Author `README.md`** (AC: #9)
  - [x] Add project name + one-paragraph description (the PRD §1 wording is fine to summarize).
  - [x] Add a "## Setup" section with the bullet list described in AC #9.
  - [x] Add stub `## Architecture overview` and `## AI integration log` sections (one sentence + a link to `_bmad-output/planning-artifacts/architecture.md`).
- [x] **Task 7 — Verify `docker compose config`** (AC: #8)
  - [x] Run `docker compose config` from the repo root.
  - [x] Confirm exit code 0 and no error output. Capture stdout in the dev log for the reviewer.
  - [x] If Compose complains about an empty services block on an `include:`d file, add a single inert `services: {}` or a commented-out stub to silence it — but do **not** introduce a real service.
- [x] **Task 8 — Preserve `CLAUDE.md`** (AC: #1)
  - [x] Verify `CLAUDE.md` at the repo root is unchanged from its current state (single Python-command convention bullet). Do **not** rewrite it; do **not** append.

## Dev Notes

### What this story is — and is not

This story is **pure repo scaffolding**. It creates the directory skeleton and the Compose entry points so every later story has a known place to add files. No application code, no Dockerfiles for services, no Keycloak realm JSON, no Angular app, no FastAPI scaffold. Those are Stories 1.2, 1.3, 1.8, 3.1, etc.

The single externally verifiable behavior is: `docker compose config` exits 0. There is no `/health` endpoint to hit yet, no service to start.

### Existing repo state at story start

The repo currently contains only:
- `_bmad/` — BMAD framework (do not touch)
- `_bmad-output/` — planning artifacts (do not touch)
- `.claude/` — Claude Code settings (do not touch)
- `.git/`
- `CLAUDE.md` — single line about using `python` (not `python3`) — **must be preserved verbatim**
- `docs/` — empty placeholder (leave as-is)

Everything else in the AC list is net-new.

### Source-of-truth references

This story is fully specified by the planning artifacts; do not infer outside them.

- **Repo layout** is defined twice and the two versions agree: [Source: `_bmad-output/planning-artifacts/architecture.md#I1. Repo structure`] (the compact view at lines 460–481) and [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure`] (the full tree at lines 865–1090). Where they differ in detail, the full tree is authoritative — but at this story's granularity (top-level dirs only) they are identical.
- **Compose composition + profiles:** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` — AR26] and [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` — I2].
- **Env vars enumerated by AR29:** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` — AR29]. Note: AR29 is post-sprint-change renumbering; the older AR30 was renamed to AR29 after observability was removed [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`].
- **`tools/` gitignored:** [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` line 1081].
- **README stubs:** [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.1` lines 251–254]; the AI integration log is filled in by Story 5.3 [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.3`].

### Constraints from the sprint-change proposal (2026-05-14)

A scope cut on 2026-05-14 removed the entire observability stack (OTEL, Jaeger, Prometheus, Grafana) [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`]. Concretely for this story:

- **Do NOT create** `compose/observability.yml`. Only two compose-include files exist: `infra.yml` and `app.yml`.
- **Do NOT add** `OTEL_EXPORT_ENABLED` or `OTEL_EXPORTER_OTLP_ENDPOINT` to `.env.example`. The AR29 list above is the complete list.
- **Profiles `default` and `dev` carry no observability trailer.**

If you see any reference to OTEL/Jaeger/Prometheus/Grafana in stale notes elsewhere, ignore it — the planning artifacts on disk are the source of truth and they are post-cut.

### Anti-patterns to avoid

- **Do not scaffold service contents.** No `pyproject.toml`, no `Dockerfile`, no `package.json`, no Keycloak realm JSON. Those come in 1.2/1.3/1.8. Putting them here pre-decides choices that belong to those stories.
- **Do not run the archetype's `build_template.py`.** That is Story 1.3 (BFF) and Story 3.1 (RS). The `tools/fastapi-archetype/` directory is gitignored and will be cloned into in Story 1.3.
- **Do not invent env vars beyond AR29.** If something seems missing, it is intentional — the corresponding service stories add their own. `.env.example` for this story tracks exactly the AR29 list.
- **Do not add CI config (`.github/workflows/`, etc.).** AR-equivalent of CI is explicitly out of scope [Source: `_bmad-output/planning-artifacts/architecture.md#I7. CI/CD`].
- **Do not introduce a `.python-version` or `.tool-versions` at the repo root.** Per-service Python pinning lives in each service's `pyproject.toml` once scaffolded.
- **Do not write a top-level `package.json` or `pyproject.toml`.** The monorepo is per-service; there is no aggregator package.
- **Do not commit any real secret.** `.env.example` only — never `.env`. The `.gitignore` must cover `.env` and `.env.local`.

### `docker compose config` validation — practical notes

The verification command is run from the repo root:

```bash
docker compose config
```

- The command must exit 0.
- Empty `include:`d files: Compose accepts `services: {}` (empty mapping). Avoid leaving the file totally empty — that triggers parse warnings.
- Profiles only need to be **named** at this stage. A defensible minimal pattern in `docker-compose.yml`:

  ```yaml
  include:
    - compose/infra.yml
    - compose/app.yml

  # Profile names are declared here so later stories attach services to them.
  # default = full stack; dev = backend-only (SPA on host); e2e = full stack + Playwright.
  x-profiles: [default, dev, e2e]
  ```

  Compose ignores top-level `x-*` extension fields, so `config` validates. As soon as a service is added (Story 1.2 introduces Keycloak), that service can carry `profiles: [default, dev, e2e]` and the documentation block becomes redundant — that is acceptable churn for a scaffold story.

- If `docker compose config` complains that `include:` cannot resolve a file: confirm paths are relative to the repo root and use forward slashes regardless of host OS.

### File-by-file targets

Final state at end of story, relative to repo root (omitting pre-existing files):

```
docker-compose.yml
.env.example
.gitignore
.dockerignore
README.md
compose/infra.yml
compose/app.yml
spa/.gitkeep
services/.gitkeep                 (optional, parent of bff/ and resource-server/)
services/bff/.gitkeep
services/resource-server/.gitkeep
keycloak/.gitkeep
e2e/.gitkeep
tools/                            (created locally; .gitignore lists tools/fastapi-archetype/, but tools/ itself is tracked via a .gitkeep so the dir exists; OR keep the whole tools/ dir untracked — either is acceptable as long as AC#2's "tools/ (gitignored)" phrasing is honored)
```

Decision left to dev judgment: whether `tools/` itself is gitignored or only `tools/fastapi-archetype/` is. The epic AC phrasing "tools/ (gitignored)" plus the architecture phrasing "fastapi-archetype/ (cloned archetype (gitignored))" together suggest **gitignore only the archetype subdirectory** — that keeps `tools/` as a known location while the cloned archetype itself stays untracked. Recommend that approach.

### Testing standards for this story

There are no application tests in scope — there is no code yet. The story's tests are operational:

1. **`docker compose config` exits 0.** Capture in dev log. This is AC #8.
2. **`git status` shows no surprising untracked files** at end of story (e.g., no `.env`, no `node_modules`, no `tools/fastapi-archetype/` content). Confirms `.gitignore` works as intended.
3. **Manual file existence check** matching the file-by-file list above.

No unit-test framework is installed yet — that lands in Stories 1.3 (pytest for BFF) and 1.8 (Vitest for SPA).

### Project Structure Notes

- The repo root is monorepo; no per-language top-level config files. Each backend service will own its own `pyproject.toml`/`uv.lock` (Story 1.3, 3.1); the SPA owns its own `package.json` (Story 1.8); E2E owns its own `package.json` (Story 1.11).
- Sub-tree paths used elsewhere in the architecture (e.g., `services/bff/src/bff/...`) are deeper than this story creates. This story stops at `services/bff/` being an empty directory; Story 1.3 fills it.
- Compose file naming uses `compose/<aspect>.yml` (not `docker-compose.<aspect>.yml`). Two files: `infra.yml` (Keycloak — Story 1.2), `app.yml` (BFF + RS + SPA — Stories 1.3, 1.8, 3.1).
- The repo intentionally has **no** `compose/observability.yml` after the 2026-05-14 scope cut.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.1: Repo scaffold + compose skeleton` lines 220–254] — the canonical story spec and ACs.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` — AR25 lines 88, AR26 line 89, AR28 line 91, AR29 line 92] — repository structure, compose composition, health checks, env vars.
- [Source: `_bmad-output/planning-artifacts/architecture.md#I1. Repo structure` lines 460–481] — compact monorepo layout.
- [Source: `_bmad-output/planning-artifacts/architecture.md#I2. Compose composition` lines 483–487] — `include:` directive + three profiles.
- [Source: `_bmad-output/planning-artifacts/architecture.md#I5. Env vars` lines 502–507] — env-var enumeration aligned with AR29.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 865–1090] — the full tree (only the top-level subset applies to this story).
- [Source: `_bmad-output/planning-artifacts/architecture.md#File Organization Patterns` lines 1252–1276] — confirms what config files belong at the root.
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`] — the observability scope cut; explicitly removes `compose/observability.yml` and the two `OTEL_*` env vars from Story 1.1's scope.
- [Source: `CLAUDE.md` at repo root] — project convention: invoke Python as `python`, never `python3`.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (Claude Code, bmad-quick-dev workflow)

### Debug Log References

`docker compose config` from repo root, baseline commit `215d84e`:

```
$ docker compose config
name: bmad_books
services: {}
x-profiles:
  - default
  - dev
  - e2e
$ echo $?
0
```

`git check-ignore -v tools/fastapi-archetype/anything` → `.gitignore:2:tools/fastapi-archetype/` (rule applied, archetype subdir correctly untracked while `tools/` itself remains tracked via `.gitkeep`).

`git status --short` after implementation shows only the planned new files and the two `_bmad-output/` spec/sprint-status edits — no `.env`, no `node_modules`, no archetype contents bleeding through.

### Completion Notes List

- Followed the dev-judgment recommendation in the spec: `tools/` is tracked (via `.gitkeep`) while only `tools/fastapi-archetype/` is gitignored. This keeps `tools/` discoverable as the known archetype location and lets Story 1.3 clone in without renaming.
- Top-level `docker-compose.yml` declares the three profile names through an inert `x-profiles: [default, dev, e2e]` extension field — Compose preserves it through `config` (visible in the validated output) and ignores it for service resolution. As soon as Story 1.2's Keycloak service lands, services can carry their own `profiles: [...]` and this anchor becomes redundant churn (called out in spec Task 5).
- `compose/infra.yml` and `compose/app.yml` use `services: {}` (empty mapping) — the spec's "Practical notes" section explicitly endorses this over an entirely empty file, and `docker compose config` accepts the include without warnings.
- `.env.example` contains exactly the 15 AR29 vars (per the post-2026-05-14 scope cut). No `OTEL_*` vars were introduced. Example values are placeholders (`change-me`) or working-dev defaults (`sqlite+aiosqlite:////data/bff.db`, `http://keycloak:8080/realms/booksapp`); no real secrets.
- `CLAUDE.md` was not touched — verified byte-for-byte against pre-story state (single `python` convention line).
- Out of scope (confirmed not done, per spec anti-patterns): no service Dockerfiles, no `pyproject.toml`/`package.json`, no Keycloak realm JSON, no CI workflow, no root `.python-version`, no archetype clone.

### File List

**New files:**
- `.gitignore`
- `.dockerignore`
- `.env.example`
- `README.md`
- `docker-compose.yml`
- `compose/infra.yml`
- `compose/app.yml`
- `spa/.gitkeep`
- `services/bff/.gitkeep`
- `services/resource-server/.gitkeep`
- `keycloak/.gitkeep`
- `e2e/.gitkeep`
- `tools/.gitkeep`

**Modified files (workflow bookkeeping only — no production change):**
- `_bmad-output/implementation-artifacts/1-1-repo-scaffold-compose-skeleton.md` — added YAML frontmatter (`status`, `baseline_commit`, `story_key`), flipped status to `in-progress`, ticked all tasks, filled Dev Agent Record.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `1-1-repo-scaffold-compose-skeleton` flipped `ready-for-dev` → `in-progress`. `epic-1` was already `in-progress` (no lift needed).

**Untouched (verified):**
- `CLAUDE.md` — preserved verbatim.
- All `_bmad/`, `_bmad-output/planning-artifacts/`, `.claude/`, `docs/` content.

## Review Findings (step-04)

Three adversarial reviewers ran in parallel.

- **Acceptance auditor:** APPROVE — all 9 ACs PASS, all cross-checks PASS (AR29 completeness, OTEL exclusion, profile-name visibility, `CLAUDE.md` preservation, observability scope cut, anti-pattern adherence), `docker compose config` exit 0.
- **Blind hunter:** 15 candidate issues raised without spec context. Classification after applying spec/dev-notes context: 13 rejected (spec-prescribed approaches the reviewer couldn't see, e.g., `x-profiles` documentation anchor; `change-me` placeholders endorsed by AC #5; `tools/.gitkeep` + archetype-subdir gitignore is the spec-recommended dev judgment), 2 collapsed into the two defers below.
- **Edge-case hunter:** 0 critical, 2 important (both deferred — see below), 2 nits (rejected: spec already permits older-Compose stderr notice on AC #8; spec authorizes the `x-profiles` placeholder).

**Patches applied:** none.

**Deferred to later stories** (recorded in [`deferred-work.md`](deferred-work.md)):

- **D1** — `.env.example` SQLite URLs target in-container `/data` only; host-side `dev` profile will hit `unable to open database file`. Owner: Stories 1.3, 3.1.
- **D2** — OIDC URLs use the Docker-DNS hostname `keycloak`; browser redirects from the host will fail without a published port + frontend-URL alias, and `OIDC_AUDIENCE == OIDC_CLIENT_ID` will fail audience validation without a Keycloak audience mapper. Owners: Stories 1.2, 1.4–1.5.

## Suggested Review Order

**Compose composition** (start here — the architectural anchor for the whole story)

- Top-level entry point: `include:` of the two tier files; profile names declared via inert `x-profiles` extension (per spec Practical Notes — Story 1.2 will move these onto services).
  [`docker-compose.yml:15`](../../docker-compose.yml#L15)
- Infra tier — Story 1.2 lands Keycloak into this empty mapping.
  [`compose/infra.yml:6`](../../compose/infra.yml#L6)
- App tier — Stories 1.3 / 1.8 / 3.1 land BFF, SPA, RS here.
  [`compose/app.yml:6`](../../compose/app.yml#L6)

**Environment contract (AR29)**

- All 15 AR29 vars present, grouped by consumer; no `OTEL_*` (post-2026-05-14 scope cut); placeholders only.
  [`.env.example:9`](../../.env.example#L9)

**Repo hygiene**

- Only `tools/fastapi-archetype/` is gitignored; `tools/` itself remains tracked via `.gitkeep` so the archetype's destination is discoverable.
  [`.gitignore:2`](../../.gitignore#L2)
- Image build context excludes the entire BMAD workspace and `tools/` (build contexts will be per-service in Stories 1.3 / 3.1).
  [`.dockerignore:6`](../../.dockerignore#L6)

**Developer onboarding**

- Setup ordering matches the planned sequence (clone → archetype → `.env` → `docker compose up`); architecture link + Story 5.3 AI integration log stub.
  [`README.md:5`](../../README.md#L5)

**BMAD bookkeeping** (no production impact)

- Sprint state lifted to `in-progress` at story start (epic-1 was already in-progress).
  [`sprint-status.yaml:47`](sprint-status.yaml#L47)
- Deferred risks from the review surface here for later story owners.
  [`deferred-work.md:1`](deferred-work.md#L1)
