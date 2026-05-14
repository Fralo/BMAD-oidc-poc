---
status: ready-for-dev
story_key: 1-2-keycloak-realm-as-code-compose-service
specLoopIteration: 1
---

# Story 1.2: Keycloak realm-as-code + compose service

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running the project,
I want Keycloak to boot with a pre-imported realm containing the BFF client, scopes, audience claim, and the two pre-seeded users,
So that authentication works on first `docker compose up` with zero manual configuration steps.

## Acceptance Criteria

**Realm content — `keycloak/realm-bmad-books.json`**

1. **The file `keycloak/realm-bmad-books.json` exists** at the repo root and defines a realm whose `realm` field is exactly `bmad-books`. Realm is `enabled: true` and `sslRequired: "none"` (so the dev http://localhost flow works).
2. **A confidential client `bmad-books-bff` is defined** with:
   - `clientId: "bmad-books-bff"`,
   - `publicClient: false`, `clientAuthenticatorType: "client-secret"`,
   - `secret` sourced from the `BFF_CLIENT_SECRET` env var (Keycloak realm-import supports `${BFF_CLIENT_SECRET}` substitution when the env var is present in the container; if not, the secret field is set to the literal env-var reference and resolved at import),
   - `standardFlowEnabled: true` (Authorization Code), `directAccessGrantsEnabled: false` (no password grant), `implicitFlowEnabled: false`, `serviceAccountsEnabled: false`,
   - `attributes.pkce.code.challenge.method = "S256"` (PKCE required),
   - `redirectUris` includes `http://localhost:8000/auth/callback` (= `BFF_BASE_URL/auth/callback`),
   - `webOrigins` includes `http://localhost:8000` (avoids browser CORS surprises in later stories).
3. **Two client scopes are defined** in the realm:
   - `reading-speed:read` with `protocol: "openid-connect"`,
   - `reading-speed:write` with `protocol: "openid-connect"`,
   and both are **assigned to the `bmad-books-bff` client as `optional`** (the BFF requests them in the `scope` param per AR2).
4. **The access token carries audience `bmad-books-resource-server`** via an audience protocol mapper on the `bmad-books-bff` client. The mapper is named (e.g.) `aud-resource-server`, of type `oidc-audience-mapper`, with `included.custom.audience = "bmad-books-resource-server"`, `id.token.claim = "false"`, `access.token.claim = "true"`. This closes D2 (issue 2) deferred from Story 1.1 — without it, the Resource Server's `aud` validation in Stories 3.2/3.3 fails. (`OIDC_AUDIENCE` in `.env.example` must therefore equal `bmad-books-resource-server`, not `OIDC_CLIENT_ID` — see AC #9.)
5. **Two test users are pre-seeded** in the realm:
   - `testuser` with `enabled: true`, `email: "testuser@example.test"`, `emailVerified: true`, and a credential `{ type: "password", value: "testpassword", temporary: false }`.
   - `freshuser` with `enabled: true`, `email: "freshuser@example.test"`, `emailVerified: true`, and a credential `{ type: "password", value: "freshpassword", temporary: false }`.
   Neither user is assigned any reading-speed value here — the RS owns that data (Stories 3.x). The `freshuser` exists specifically to exercise the J3 `412 reading_speed_unset` precondition path in Epic 4.

**Container — `keycloak/Dockerfile`**

6. **`keycloak/Dockerfile` wraps the official Keycloak image** (recommended: `quay.io/keycloak/keycloak:26.0` — current stable as of 2026-05-14; any 26.x is acceptable). It:
   - copies `realm-bmad-books.json` into `/opt/keycloak/data/import/realm-bmad-books.json`,
   - sets entrypoint/command to `start-dev --import-realm` (this project is an educational demo running over http://localhost; `start --import-realm --optimized` is documented in dev notes as the prod-mode alternative but is NOT required for this story),
   - declares a `HEALTHCHECK` (or relies on a compose-level healthcheck — see AC #7) that polls `http://localhost:9000/health/ready` (Keycloak 25+ exposes management endpoints on port 9000 by default; see dev notes).

**Compose wiring — `compose/infra.yml`**

7. **`compose/infra.yml` defines a `keycloak` service** with:
   - `build: { context: ./keycloak }` (or `image:` if the Dockerfile is built externally — `build:` is the canonical choice per the AR1/AR26 pattern),
   - `container_name: keycloak` (so Docker DNS resolves it as `keycloak` from BFF/RS containers, matching `OIDC_ISSUER_URL=http://keycloak:8080/...`),
   - `env_file:` references the repo-root `.env` (to inject `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`),
   - additional env: `KC_HOSTNAME=localhost`, `KC_HOSTNAME_STRICT=false`, `KC_HTTP_ENABLED=true`, `KC_HEALTH_ENABLED=true` (the last enables `:9000/health/*`),
   - `ports: ["8080:8080"]` so the browser on the host can reach the admin console and the OIDC `/auth` redirect (BFF→Keycloak is on the Docker network at `keycloak:8080`),
   - `healthcheck:` curling `http://localhost:9000/health/ready` until 200 (interval ≤ 10s, retries ≥ 12 — realm import takes ~30–60s on a cold start),
   - `profiles: [default, dev, e2e]` (Keycloak runs in **all** three profiles — it is the auth dependency; the `dev` profile only excludes the SPA, not Keycloak, per AR26 and Story 1.1's `docker-compose.yml` header comment),
   - `restart: unless-stopped`.

**`.env.example` reconciliation — fixes D2 from Story 1.1**

8. **`.env.example` OIDC values are updated** so the realm/client/audience names match the realm imported above:
   - `OIDC_ISSUER_URL=http://keycloak:8080/realms/bmad-books` (was `…/realms/booksapp`),
   - `OIDC_JWKS_URL=http://keycloak:8080/realms/bmad-books/protocol/openid-connect/certs` (was `…/realms/booksapp/...`),
   - `OIDC_CLIENT_ID=bmad-books-bff` (was `bff-client`),
   - `OIDC_AUDIENCE=bmad-books-resource-server` (was `bff-client` — this is the second half of D2's fix; `OIDC_AUDIENCE` must equal the audience the realm's mapper adds, NOT the client id).
   No new vars are introduced; the AR29 list is unchanged.

**Boot verification**

9. **`docker compose up keycloak` succeeds end-to-end**, demonstrated by these four checks captured in the dev log:
   - `docker compose config` exits 0 with the `keycloak` service visible under `services:`.
   - `curl -fsS http://localhost:9000/health/ready` returns 200 within the healthcheck window after `docker compose up keycloak`.
   - **Direct realm verification** (purely for human verification — the BFF will NOT use this grant): a `POST http://localhost:8080/realms/bmad-books/protocol/openid-connect/token` with `grant_type=password`, `client_id=bmad-books-bff`, `client_secret=$BFF_CLIENT_SECRET`, `username=testuser`, `password=testpassword`, `scope=openid offline_access reading-speed:read reading-speed:write` is **expected to fail with `unauthorized_client` / `Direct access grants disabled`** (because AC #2 forbids `directAccessGrantsEnabled`). This is the right outcome — it proves password grant is off. For positive token verification, use the admin console at `http://localhost:8080/admin/` (login with `KEYCLOAK_ADMIN_USER`/`KEYCLOAK_ADMIN_PASSWORD`) and confirm: realm `bmad-books` exists; client `bmad-books-bff` is configured with PKCE S256, the two `reading-speed:*` scopes, and the audience mapper to `bmad-books-resource-server`; users `testuser` and `freshuser` are present.
   - No manual configuration is required after `docker compose up keycloak` — i.e., the four bullets above succeed on the **first** `up` against an empty `keycloak_data` volume (if one is used; the realm JSON re-imports on every start in `start-dev --import-realm`, so a wiped volume is the normal case).

## Tasks / Subtasks

- [ ] **Task 1 — Author the realm JSON `keycloak/realm-bmad-books.json`** (AC: #1, #2, #3, #4, #5)
  - [ ] Start from a minimal hand-written Keycloak realm export shape (do NOT export from a running Keycloak admin console — that produces hundreds of irrelevant fields; keep the file minimal and reviewable).
  - [ ] Define `realm: "bmad-books"`, `enabled: true`, `sslRequired: "none"`, sensible `accessTokenLifespan` (e.g., 300s) and `ssoSessionIdleTimeout` (e.g., 1800s).
  - [ ] Add the `bmad-books-bff` client per AC #2 (confidential + PKCE S256 + Auth Code only). Set `secret: "${BFF_CLIENT_SECRET}"` — Keycloak's realm-import resolves `${VAR}` against container env when the env var is present.
  - [ ] Add the audience protocol mapper to the `bmad-books-bff` client per AC #4 (`oidc-audience-mapper`, custom audience `bmad-books-resource-server`, `access.token.claim=true`, `id.token.claim=false`).
  - [ ] Define the two client scopes (`reading-speed:read`, `reading-speed:write`) at the realm level and add them to the client's `optionalClientScopes` array.
  - [ ] Add the two users (`testuser`, `freshuser`) with the credentials in AC #5. Use `"temporary": false` so they don't trigger first-login password reset.
- [ ] **Task 2 — Author `keycloak/Dockerfile`** (AC: #6)
  - [ ] `FROM quay.io/keycloak/keycloak:26.0` (or current 26.x).
  - [ ] `COPY realm-bmad-books.json /opt/keycloak/data/import/realm-bmad-books.json`.
  - [ ] `CMD ["start-dev", "--import-realm"]` (entrypoint is inherited from the base image).
  - [ ] Document inline (a short header comment) that prod-mode uses `start --import-realm --optimized` and requires a build stage (`kc.sh build`) — out of scope for this educational project per architecture I3.
- [ ] **Task 3 — Wire the `keycloak` service into `compose/infra.yml`** (AC: #7)
  - [ ] Replace the empty `services: {}` mapping with a real `keycloak:` service per AC #7's bullet list.
  - [ ] Set `KC_HOSTNAME=localhost` and `KC_HOSTNAME_STRICT=false` — these are the **only** Keycloak 26 settings required to make `http://localhost:8080` the public-facing URL while keeping internal Docker-DNS access at `http://keycloak:8080` valid. (Browser-vs-container hostname reconciliation in tokens is finalized in Stories 1.4/1.5 — see Dev Notes.)
  - [ ] Set `KC_HEALTH_ENABLED=true` so `:9000/health/ready` returns 200 once the realm import is complete.
  - [ ] Configure the healthcheck: `test: ["CMD", "curl", "-fsS", "http://localhost:9000/health/ready"]`, `interval: 10s`, `timeout: 5s`, `retries: 30`, `start_period: 30s`. Note that the official Keycloak image does NOT ship `curl`; use the alternate `["CMD-SHELL", "exec 3<>/dev/tcp/localhost/9000 && printf 'GET /health/ready HTTP/1.0\\r\\n\\r\\n' >&3 && cat <&3 | grep -q '200 OK'"]` form, OR install curl in the `keycloak/Dockerfile`, OR use a tiny `keycloak-healthcheck` companion via `depends_on.condition` only on later services. **Recommended approach**: install `curl` in `keycloak/Dockerfile` (`USER 0 && microdnf install -y curl && USER 1000`) — keeps the compose healthcheck readable and matches the AR28 pattern. Document the choice in the Dockerfile.
  - [ ] Add `profiles: [default, dev, e2e]` on the service. As soon as this lands, the inert `x-profiles:` extension at the bottom of the repo-root `docker-compose.yml` becomes redundant; **leave the `x-profiles:` line in place for this story** — Story 1.1 documented the churn; remove it in Story 1.3 once a second service joins, to avoid a noisy diff here. (Single-service refactors should not happen mid-story.)
- [ ] **Task 4 — Update `.env.example` to match the realm** (AC: #8)
  - [ ] Edit the four OIDC lines per AC #8 (`OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_CLIENT_ID`, `OIDC_AUDIENCE`).
  - [ ] Leave every other variable untouched; do NOT reorder, do NOT add new vars, do NOT remove the `change-me` placeholders (those are the subject of D3, deferred again here — see Dev Notes).
- [ ] **Task 5 — Verify `docker compose config`** (AC: #9 bullet 1)
  - [ ] Run `docker compose config` from the repo root.
  - [ ] Confirm exit code 0 and that the rendered output contains the `keycloak` service with `ports`, `env_file`, `healthcheck`, and `profiles` populated.
  - [ ] Capture the relevant stdout slice in the dev log.
- [ ] **Task 6 — Verify Keycloak boots and the realm imports** (AC: #9 bullets 2–4)
  - [ ] `cp .env.example .env` (if `.env` does not already exist locally; `.env` is gitignored).
  - [ ] `docker compose up keycloak -d` (note: Compose's `up` of a single service still requires the service to be in an active profile; pass `--profile dev` or `--profile default` explicitly).
  - [ ] Poll `curl -fsS http://localhost:9000/health/ready` until 200 (allow up to ~90s on first boot; the realm import is the slow step).
  - [ ] Visit `http://localhost:8080/admin/` in a browser; log in with `${KEYCLOAK_ADMIN_USER}`/`${KEYCLOAK_ADMIN_PASSWORD}`; confirm realm `bmad-books` exists, the `bmad-books-bff` client is configured per AC #2/#3/#4, and users `testuser`/`freshuser` are present.
  - [ ] Run the negative password-grant check (AC #9 bullet 3) and confirm `unauthorized_client` — this proves direct grants are off.
  - [ ] Capture all four verifications in the dev log.
- [ ] **Task 7 — Documentation touch in `README.md`** (no separate AC — supports AC #9 "no manual configuration required")
  - [ ] Add a short paragraph under the existing "## Setup" section: after `docker compose up`, Keycloak's admin console is at `http://localhost:8080/admin/` and the realm `bmad-books` is pre-imported with two test users (`testuser`/`testpassword`, `freshuser`/`freshpassword`).
  - [ ] Do NOT add a separate `## Keycloak` section yet — that level of structure belongs to README polish (Story 5.3).

## Dev Notes

### What this story is — and is not

This story stands up Keycloak as a real, running compose service with a version-controlled realm. After it lands, `docker compose up keycloak` works end-to-end and the admin console is browsable. **This story does NOT exercise OIDC flows from any app** — there is no BFF yet (Story 1.3), no `/auth/login` (Story 1.5), no SPA (Story 1.8). The only externally verifiable behaviors are: (a) Keycloak's `/health/ready` returns 200, (b) the admin console shows the expected realm/client/users, (c) a direct password-grant attempt fails with `unauthorized_client` (proving direct grants are off).

The realm JSON is the **single source of truth** for the auth configuration — it is committed to git, reviewed via PRs, and re-imported on every container start. There is no admin-console clickops in this project.

### Existing repo state at story start

The repo currently contains the Story 1.1 scaffold:
- `keycloak/.gitkeep` — placeholder; this story replaces it with the realm JSON + Dockerfile.
- `compose/infra.yml` — `services: {}` placeholder; this story lands the `keycloak:` service into it.
- `docker-compose.yml` — `include:`s both compose files, declares the three profiles via the inert `x-profiles: [default, dev, e2e]` documentation anchor. Keep that anchor for now; remove it when a second service joins in Story 1.3.
- `.env.example` — has all 15 AR29 vars but the OIDC values use placeholder names (`booksapp`, `bff-client`). This story aligns them to the real realm/client/audience names.
- No service code exists yet; `services/bff/` and `services/resource-server/` are empty `.gitkeep` directories.

### Source-of-truth references

This story is fully specified by the planning artifacts; do not infer beyond them.

- **Story-level scope and ACs:** [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.2: Keycloak realm-as-code + compose service` lines 255–282].
- **AR27 — Keycloak realm-as-code shape (client, scopes, audience, users):** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` line 90].
- **AR26 — Compose composition + three profiles:** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` line 89].
- **AR28 — Health checks + `depends_on: service_healthy` ordering:** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` line 91].
- **AR29 — Env vars (no new vars; only value alignment in `.env.example`):** [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` line 92].
- **I3 — Realm-as-code architectural detail:** [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` lines 489–495].
- **I4 — Two test users and the rationale for `freshuser`:** [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` lines 497–500].
- **A1 — Scope set requested at `/authorize` (`reading-speed:read`/`write` are optional client scopes):** [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` line 347].
- **A2 — Why the audience claim mapper is critical (RS validates `aud`):** [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` line 348] and [Source: `_bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis` line 536].
- **Repo layout for `keycloak/`:** [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 878–880].
- **PRD principles 7–8 — identity SoT + reproducible auth-server config:** [Source: `_bmad-output/planning-artifacts/PRD.md` lines 81–84].
- **Deferred from Story 1.1 — D2 (audience mapper + `.env.example` alignment), D3 (placeholder-credential refusal):** [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D2, D3].
- **Story 1.1 inheritance — `docker-compose.yml`, `.env.example`, `compose/infra.yml` starting state:** [Source: `_bmad-output/implementation-artifacts/1-1-repo-scaffold-compose-skeleton.md` File List + Suggested Review Order].
- **Project convention — invoke Python as `python`:** [Source: `CLAUDE.md` at repo root].

### Closing D2 (deferred from Story 1.1)

Story 1.1's review surfaced D2 — the audience mapper was not yet defined, and `.env.example` had `OIDC_AUDIENCE=bff-client` which would never appear in the access token's `aud` claim by default. This story closes the **realm side** of D2:

- The audience mapper on `bmad-books-bff` adds `bmad-books-resource-server` to the access token's `aud` claim (AC #4).
- `.env.example` is updated so `OIDC_AUDIENCE=bmad-books-resource-server` (AC #8), matching what the mapper emits — this is what the RS will validate against in Story 3.2.

What this story does **not** close is the **browser-vs-container hostname split** also raised under D2: BFF→Keycloak resolves `keycloak:8080` via Docker DNS, but the browser cannot. The mitigations available are (a) publish the port `8080:8080` (this story does), and (b) set `KC_HOSTNAME=localhost` so Keycloak emits issuer/redirect URLs using `localhost:8080` (this story does, via the `keycloak` service env). The full reconciliation — making sure the JWT `iss` claim matches `OIDC_ISSUER_URL` in the BFF as seen during back-channel calls — lives in Stories 1.4/1.5 where the BFF actually does an OIDC discovery + token exchange. **Do not preemptively split `OIDC_ISSUER_URL` into "external" and "internal" variants in this story** — that decision belongs to 1.4/1.5 and committing it here would lock in a shape the BFF stories may want to reshape.

### D3 (placeholder-credential refusal) — explicitly NOT closed here

Story 1.1's review also surfaced D3 — `change-me` placeholders boot silently. The deferred-work record names Story 1.2 as a potential owner for the Keycloak side ("refuse boot if `KEYCLOAK_ADMIN_PASSWORD == change-me` outside the dev profile"). **For this story, leave D3 deferred** for three reasons:

1. The current project does not differentiate "dev profile" from "prod profile" for Keycloak — Keycloak runs in all three profiles per AR26. There is no clean "outside the dev profile" boundary here.
2. The Story 1.2 ACs (epics.md lines 261–282) do not include a runtime refuse-to-boot guard; adding one expands scope.
3. The educational nature of the project (PRD §12: success = `docker compose up` reproducibility on a contributor's laptop) is not well served by aggressive startup refusal — the README setup steps already tell the contributor to set real values.

If the dev runs the verification flow and notices that `change-me` happily boots, that is the expected state for this story. The defer is preserved in `deferred-work.md`.

### Keycloak version + image notes (latest tech)

- **Recommended image:** `quay.io/keycloak/keycloak:26.0` (the official image as of 2026-05-14; the `26.x` line has been the stable line since late 2024 and supports `--import-realm`, the `KC_*` env-driven config model, and the `:9000/health` management endpoints out of the box).
- **Avoid `latest` tag** — pin to a concrete minor (`26.0` or `26.1` if released) so the image hash is reproducible across contributors.
- **`KC_HEALTH_ENABLED=true`** turns on `:9000/health`, `:9000/health/ready`, `:9000/health/live` (Keycloak 25+ split management endpoints onto port 9000). Without this flag the healthcheck silently 404s.
- **`KC_HOSTNAME=localhost` + `KC_HOSTNAME_STRICT=false`** is the minimal "make http://localhost:8080 work as the public face" combination in 26.x. `KC_HOSTNAME_STRICT_HTTPS=false` is NOT needed in 26.x (the flag was retired).
- **`start-dev --import-realm`** is correct for this educational project. It boots with the dev SSL stance (`sslRequired=NONE`), uses an in-memory H2-backed cache, and re-imports the realm on every start. The `start --import-realm --optimized` (prod-mode) path requires a multi-stage build (`kc.sh build` in a builder stage) and is **explicitly out of scope** for this story.
- **`--import-realm` flag** picks up any `*.json` file under `/opt/keycloak/data/import/`. Be sure the realm file is copied there in the Dockerfile — putting it under `/opt/keycloak/data/` (without `/import/`) is a common mistake that silently skips the import.
- **`curl` is not in the base image.** Either install it (`microdnf install -y curl`) or use the CMD-SHELL `/dev/tcp` form. The recommended path is to install curl — keeps the healthcheck readable and matches the AR28 pattern future services will use.

### Anti-patterns to avoid

- **Do not scaffold any BFF or RS code in this story.** No `pyproject.toml`, no `Dockerfile` under `services/`, no `archetype` clone. Those are Stories 1.3 and 3.1.
- **Do not export the realm JSON from a running Keycloak admin console.** That produces hundreds of internal fields (UUIDs, `clientPolicies`, default flows, etc.) which bloat the diff and obscure intent. Hand-write a minimal JSON containing exactly what AC #1–#5 require, and let Keycloak fill in defaults during import.
- **Do not commit a real `BFF_CLIENT_SECRET` or `KEYCLOAK_ADMIN_PASSWORD`.** The realm JSON uses `${BFF_CLIENT_SECRET}` so the secret is resolved from container env at import time. `.env.example` still ships with `change-me` placeholders; only the developer's local `.env` ever holds real values.
- **Do not enable `directAccessGrantsEnabled` on the BFF client** (i.e., the password grant). The architecture explicitly forbids it (§ "Auth Code + PKCE flow is mandatory; implicit flow and password grant are forbidden by §8" — architecture line 62). AC #9 bullet 3 actively *verifies* it is off.
- **Do not enable `serviceAccountsEnabled` or `implicitFlowEnabled` on the BFF client.** Same rationale.
- **Do not add a database container for Keycloak** (PostgreSQL/MariaDB). `start-dev` uses the embedded H2 store; for an educational demo we do not need persistence beyond the import. Adding a DB triples the cold-boot time and adds no value to the OAuth demonstration.
- **Do not add additional users beyond `testuser` and `freshuser`.** The two users are deliberately chosen to exercise specific journeys (`freshuser` for the J3 412 path). Extra users add fixtures the E2E tests have not been written against.
- **Do not split `OIDC_ISSUER_URL` into internal/external variants here.** That decision belongs to Stories 1.4/1.5 — see D2 notes above.
- **Do not preemptively assign the two `reading-speed:*` scopes as `default` instead of `optional`.** The BFF requests them in the `scope` parameter at `/authorize` (per A1/AR2). Assigning them as `default` would mask a future bug where the BFF forgets to request a scope and still receives it.
- **Do not introduce admin-console clickops.** Every change to the realm — including future ones like adding a `prod` redirect URI — goes through edits to `realm-bmad-books.json` reviewed in a PR.

### File-by-file targets

New / modified files at end of story, relative to repo root:

```
keycloak/Dockerfile                       NEW
keycloak/realm-bmad-books.json            NEW
keycloak/.gitkeep                         DELETE (no longer needed; the dir has real content)
compose/infra.yml                         UPDATE (services: {} → services: { keycloak: ... })
.env.example                              UPDATE (4 OIDC lines, per AC #8)
README.md                                 UPDATE (one short paragraph under ## Setup, per Task 7)
```

Untouched (verify byte-for-byte):
- `CLAUDE.md` — preserved.
- `docker-compose.yml` — the inert `x-profiles:` anchor stays in for this story; it's removed in 1.3 when a second service joins.
- `compose/app.yml` — still `services: {}` until Story 1.3.
- `.gitignore`, `.dockerignore` — no changes.

### Testing standards for this story

There is no application code in scope — there is no Python or TypeScript project yet. The story's tests are operational:

1. **`docker compose config` exits 0** with the keycloak service rendered (AC #9 bullet 1). Capture in dev log.
2. **`http://localhost:9000/health/ready` returns 200** within ~90s of `docker compose up keycloak` against a fresh state (AC #9 bullet 2). Capture in dev log.
3. **Admin-console inspection** confirms realm/client/scopes/audience-mapper/users (AC #9 bullet 3). Capture screenshots OR a short bullet checklist in the dev log.
4. **Password-grant negative check** returns `unauthorized_client` (AC #9 bullet 3). Capture the full `curl -v` response in the dev log.
5. **`git status` is clean** after the story — only the planned new/modified files appear; no `.env`, no stray Keycloak data files, no `tools/fastapi-archetype/` bleed-through.

No pytest/Vitest framework is in scope yet — those land in 1.3 (pytest), 1.8 (Vitest), 1.11 (Playwright).

### Previous story intelligence (from Story 1.1)

Story 1.1 was the scaffold-only story; key learnings carried forward:

- **The `x-profiles: [default, dev, e2e]` anchor in `docker-compose.yml` is intentional and survives `docker compose config`.** When the first real service lands (this story), service-level `profiles: [...]` and the top-level anchor coexist — the anchor stops carrying meaning but does no harm. Leave it for this story; remove it in Story 1.3.
- **The Story 1.1 review surfaced D1 (SQLite paths assume `/data` in-container) which is owned by 1.3/3.1 — not this story.** Do not touch the SQLite URLs in `.env.example`; the four lines changed in AC #8 are the only `.env.example` edits in scope.
- **Story 1.1 preserved `CLAUDE.md` verbatim.** Do the same here.
- **Story 1.1 chose `tools/.gitkeep` + `tools/fastapi-archetype/` gitignore** (rather than gitignoring all of `tools/`). That decision stands; this story does not touch `tools/`.
- **Story 1.1 captured `docker compose config` output in the dev log** as the AC #8 evidence. Match that pattern for this story's verifications (Task 5 and Task 6).

### Git intelligence (recent commits)

Recent commits on this branch (`story-1-2`, branched from `main` after Story 1.1):

```
3ec36be finished story 1.1
8f27b32 feat: implement story 1.1 — repo scaffold + compose skeleton
215d84e feat: story 1.1
489796f feat: implementation readiness
e0227e0 feat: debriefed and created architecture
```

Story 1.1's two implementation commits (`215d84e` baseline, `8f27b32` substantive work, `3ec36be` close-out) are the immediate prior art for compose authoring conventions in this repo: top-of-file header comments explaining what each file owns, inline rationale for non-obvious choices (e.g., the `x-profiles` anchor), and dev-log capture of validation command output. Match that prose style.

### Project Structure Notes

- `keycloak/` becomes a real subdirectory (no longer just `.gitkeep`) with two files: the realm JSON and the Dockerfile. No further nesting.
- `compose/infra.yml` is the **only** compose file that gains a service in this story. `compose/app.yml` remains empty until Story 1.3.
- Per-service `.env` files are gitignored (`.gitignore` `**/.env` with `!**/.env.example` whitelist). For Keycloak we use the **repo-root** `.env` via `env_file:` rather than a `keycloak/.env` — the keycloak vars are already in the root `.env.example` (`KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`) and there is no need for a per-service env split. This is consistent with AR29's "single `.env.example` at repo root" and the simpler intent of the educational project.

### References

- [Source: `_bmad-output/planning-artifacts/epics.md#Story 1.2: Keycloak realm-as-code + compose service` lines 255–282] — canonical story spec, including the three BDD blocks reorganized into ACs above.
- [Source: `_bmad-output/planning-artifacts/epics.md#Additional Requirements` lines 89–92] — AR26 (compose), AR27 (realm-as-code), AR28 (healthchecks), AR29 (env vars).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Infrastructure & Deployment` lines 460–513] — I1–I8: repo structure, compose composition, realm-as-code, test users, env vars, persistence.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` lines 343–354] — A1 (Authlib + scopes), A2 (PyJWT + audience), A3 (PKCE storage), A4 (cookie attrs); explains why the audience mapper is non-negotiable.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Decision Impact Analysis` lines 515–536] — implementation sequence + the "BFF→RS audience claim mapping (I3) must be in place before the RS can validate `aud`" cross-component note.
- [Source: `_bmad-output/planning-artifacts/architecture.md#Complete Project Directory Structure` lines 866–890] — the `keycloak/` subtree (`realm-bmad-books.json` + `Dockerfile`).
- [Source: `_bmad-output/planning-artifacts/PRD.md` lines 56–84] — the high-level auth topology principles, including "Reproducible authorization server configuration" and "Identity source of truth".
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md` D2, D3] — what this story closes (D2 realm-side) vs. what it leaves deferred (D2 hostname split → 1.4/1.5; D3 placeholder credentials → deferred again).
- [Source: `_bmad-output/implementation-artifacts/1-1-repo-scaffold-compose-skeleton.md`] — inherited state of `compose/infra.yml`, `.env.example`, `docker-compose.yml`, and the `x-profiles` anchor convention.
- [Source: `CLAUDE.md` at repo root] — project convention: invoke Python as `python`, never `python3` (relevant if any dev-log verification uses Python helpers).

## Dev Agent Record

### Agent Model Used

_To be filled by the dev agent (e.g., `claude-opus-4-7`)._

### Debug Log References

_To be filled by the dev agent. Expected captures:_

- `docker compose config` output slice showing the rendered `keycloak` service (AC #9 bullet 1).
- `curl -fsS http://localhost:9000/health/ready` first-200 response with timestamp (AC #9 bullet 2).
- Admin-console verification checklist for realm/client/scopes/audience-mapper/users (AC #9 bullet 3).
- `curl -v -X POST` of the password-grant negative case returning `unauthorized_client` (AC #9 bullet 3).
- `git status --short` showing only the planned new/modified files.

### Completion Notes List

_To be filled by the dev agent._

### File List

_To be filled by the dev agent. Expected list:_

- `keycloak/realm-bmad-books.json` (new)
- `keycloak/Dockerfile` (new)
- `keycloak/.gitkeep` (deleted)
- `compose/infra.yml` (modified — `keycloak` service added)
- `.env.example` (modified — 4 OIDC lines updated)
- `README.md` (modified — short Keycloak setup note under `## Setup`)
- `_bmad-output/implementation-artifacts/1-2-keycloak-realm-as-code-compose-service.md` (this file — status + dev record updates)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips for this story)
