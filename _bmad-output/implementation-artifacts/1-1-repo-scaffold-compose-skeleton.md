# Story 1.1: Repo scaffold + compose skeleton

Status: ready-for-dev

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

- [ ] **Task 1 — Create top-level directories** (AC: #2)
  - [ ] Create `spa/`, `services/bff/`, `services/resource-server/`, `keycloak/`, `e2e/`, `compose/`, `tools/` at the repo root. Use `.gitkeep` files (single empty file inside each empty directory) so Git tracks them.
- [ ] **Task 2 — Author `.gitignore` and `.dockerignore`** (AC: #6, #7)
  - [ ] Write `.gitignore` covering `tools/fastapi-archetype/`, per-service `.env`, Python/Node/Angular/test-tool artifacts, OS files, SQLite DB files.
  - [ ] Write `.dockerignore` covering `.git`, `_bmad/`, `_bmad-output/`, `tools/`, Node/Python caches, `dist/`, `.env*`.
- [ ] **Task 3 — Author `.env.example`** (AC: #5)
  - [ ] List every AR29 env var with a placeholder or working example. Group with comment headers (Keycloak, BFF, RS, OIDC, cookies, test-reset).
  - [ ] Confirm no real secrets are present; use literal placeholder strings like `change-me` or `<your-...>`.
- [ ] **Task 4 — Author `compose/infra.yml` and `compose/app.yml` scaffolds** (AC: #3)
  - [ ] Each file: valid Compose YAML; specify a Compose `name:` or rely on the top-level project name; include `services: {}` (or a commented stub) so the file is parseable. Do **not** declare any services yet.
- [ ] **Task 5 — Author top-level `docker-compose.yml`** (AC: #4)
  - [ ] Use `include:` pointing to both `compose/infra.yml` and `compose/app.yml`.
  - [ ] Declare the three profile names — `default`, `dev`, `e2e` — in a way that survives `docker compose config`. Pragmatic approach: add a top-level `x-profiles: [default, dev, e2e]` extension field as a self-documenting placeholder, **or** add an inert `services:` block that references the profiles, **or** declare them via the first service added later. For this story the minimum is that the three profile names appear in the file in a form a later reader can recognize as intent. The verification AC is the `docker compose config` validation in Task 7.
- [ ] **Task 6 — Author `README.md`** (AC: #9)
  - [ ] Add project name + one-paragraph description (the PRD §1 wording is fine to summarize).
  - [ ] Add a "## Setup" section with the bullet list described in AC #9.
  - [ ] Add stub `## Architecture overview` and `## AI integration log` sections (one sentence + a link to `_bmad-output/planning-artifacts/architecture.md`).
- [ ] **Task 7 — Verify `docker compose config`** (AC: #8)
  - [ ] Run `docker compose config` from the repo root.
  - [ ] Confirm exit code 0 and no error output. Capture stdout in the dev log for the reviewer.
  - [ ] If Compose complains about an empty services block on an `include:`d file, add a single inert `services: {}` or a commented-out stub to silence it — but do **not** introduce a real service.
- [ ] **Task 8 — Preserve `CLAUDE.md`** (AC: #1)
  - [ ] Verify `CLAUDE.md` at the repo root is unchanged from its current state (single Python-command convention bullet). Do **not** rewrite it; do **not** append.

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

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
