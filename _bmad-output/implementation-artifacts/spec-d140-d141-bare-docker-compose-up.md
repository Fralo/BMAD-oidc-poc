---
title: 'Make bare `docker compose up` work for a fresh clone (D140 + D141)'
type: 'bugfix'
created: '2026-05-18'
baseline_commit: '5f9b0f7'
status: 'done'
context:
  - '{project-root}/_bmad-output/implementation-artifacts/deferred-work.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The README's first-touch path (`cp .env.example .env && docker compose up`) does not actually work for a fresh clone. Two doc-vs-code drifts surfaced in Story 5.4's smoke run. **D140:** every backend service in `compose/app.yml` + `compose/infra.yml` declares `profiles: [default, dev, e2e]`, so bare `docker compose up` exits with `no service selected` on Compose v5.1.3 — contrary to README line 162's auto-activation claim. **D141:** `compose/app.yml` references per-service `.env` files (`services/bff/.env`, `services/resource-server/.env`) that the README does not document; the operator gets `env file not found` before any container starts.

**Approach:** Make bare `docker compose up` the canonical bring-up. (a) Drop `default` / `dev` from the backend services' profile lists so they run by default; keep `playwright` on `[e2e]`. (b) Route both services through the root `.env`; move topology-driven values (OIDC URLs, base URLs, DB paths, APP_NAME) into compose `environment:` blocks; delete the per-service `.env.example` templates. (c) Update README, root `.env.example` header, architecture.md, and the Justfile to reflect the new canonical command.

## Boundaries & Constraints

**Always:**
- A fresh clone must reach a healthy stack via exactly two commands: `cp .env.example .env` then `docker compose up`.
- BFF and RS must continue to receive their currently-correct `OIDC_ISSUER_URL` values: BFF gets the back-channel `http://keycloak:8080/...` for Authlib token exchange; RS gets the host-facing `http://localhost:8080/...` to match the `iss` claim Keycloak signs (Keycloak's `KC_HOSTNAME=localhost`).
- `just e2e-up` continues to work unchanged. The `compose/app.e2e.yml` overlay continues to apply the `ENABLE_TEST_RESET=true` + `TEST_RESET_TOKEN` + `AUTH_TYPE=oidc_bearer` overrides under the `e2e` profile.
- The seeded Keycloak users (`testuser`, `freshuser`) and the J1–J6 journey contracts remain intact — this is plumbing, not behavior.
- Existing pin-tests and unit tests in `services/bff/tests/` and `services/resource-server/tests/` must continue to pass (BFF/RS source code is not edited).

**Ask First:**
- If `services/bff/.env` or `services/resource-server/.env` contain operator-edited secrets distinct from the root `.env`, surface them before deletion.
- If the root `.env.example` is missing any var that lives in a per-service template (after stripping topology constants), surface it before deleting the per-service templates.

**Never:**
- Do NOT touch BFF or RS source code. This is a compose/docs fix.
- Do NOT change service-to-service URLs, OIDC audience, cookie attributes, CSRF behavior, or healthcheck probes.
- Do NOT address D142 (RS `AUTH_TYPE=none` under default profile) — adjacent but out of scope; stays deferred.
- Do NOT introduce a `just env-init` recipe; the new model removes the need for one.
- Do NOT change Keycloak admin credentials, BFF_CLIENT_SECRET, or TEST_RESET_TOKEN handling — they remain root-`.env`-driven.

</frozen-after-approval>

## Code Map

- `compose/app.yml` -- drop `profiles:` on `bff` (line 57) and `resource-server` (line 102); replace `env_file: ../services/<svc>/.env` (lines 34-35, 86-87) with `env_file: ../.env`; add `environment:` block per service for topology constants (APP_NAME, DEBUG, OIDC_ISSUER_URL split, RS_BASE_URL, BFF_DATABASE_URL, RS_DATABASE_URL, BFF_BASE_URL, OIDC_JWKS_URL, OIDC_AUDIENCE, OIDC_CLIENT_ID, OIDC_AUTHORIZE_URL_BROWSER, BFF_SESSION_COOKIE_*); update header comment.
- `compose/infra.yml` -- drop `profiles: [default, dev, e2e]` on `keycloak` (line 57); update header comment.
- `compose/app.e2e.yml` -- no functional change; verify the overlay still applies cleanly under `--profile e2e`.
- `docker-compose.yml` -- update header comment to reflect new profile semantics (only `e2e` exists; `default` and `dev` are retired).
- `.env.example` -- rewrite header to admit it is the single canonical entry point; trim to operator-controlled values only (KEYCLOAK admin, BFF_CLIENT_SECRET, TEST_RESET_TOKEN, BFF_SESSION_COOKIE_SECURE override).
- `services/bff/.env.example` -- DELETE.
- `services/resource-server/.env.example` -- DELETE.
- `services/bff/.env` -- DELETE if present (gitignored).
- `services/resource-server/.env` -- DELETE if present (gitignored).
- `README.md` -- step 3 (line 19): re-affirm root-only `.env`; step 4 (line 24): keep `docker compose up`, drop "default profile" parenthetical; troubleshooting (line 31, 33): keep; "Dev workflow" (line 86): replace `docker compose --profile dev up` with `docker compose up`; "Prod-shaped workflow" (line 159): `docker compose up --build`; line 162: rewrite — auto-activation claim becomes vacuous (no `default` profile exists anymore); project-structure section if it mentions the per-service env files.
- `_bmad-output/planning-artifacts/architecture.md` -- line 1294 region: drop the "# default profile" comment from the `docker compose up` example.
- `Justfile` -- rename `default-config` to `config` and drop `--profile default`; update preamble comments.

## Tasks & Acceptance

**Execution:**
- [x] `compose/app.yml` -- drop profile scoping on bff + RS; route via root `.env`; add per-service `environment:` blocks covering all currently-loaded topology vars from the deleted templates.
- [x] `compose/infra.yml` -- drop `profiles:` on keycloak.
- [x] `.env.example` -- rewrite header; reduce to operator-controlled vars only.
- [x] `services/bff/.env.example` + `services/resource-server/.env.example` -- delete both files.
- [x] `services/bff/.env` + `services/resource-server/.env` -- delete if present locally.
- [x] `README.md` -- update setup step 3, step 4, line 162 auto-activation paragraph, "Dev workflow" section, "Prod-shaped workflow" section; verify no other section references the per-service env files.
- [x] `_bmad-output/planning-artifacts/architecture.md` -- update the line 1294 region's `docker compose up` example comment.
- [x] `Justfile` -- rename `default-config` to `config`, drop `--profile default`; refresh preamble comment about which profile foot-guns still exist.
- [x] `docker-compose.yml` -- update header comment to reflect that `default` and `dev` profiles are retired; only `e2e` remains.

**Acceptance Criteria:**
- Given a fresh clone with no `.env` files anywhere, when the operator runs `cp .env.example .env` then edits `.env` to set real values for KEYCLOAK_ADMIN_PASSWORD / BFF_CLIENT_SECRET, when they run `docker compose up`, then keycloak + bff + resource-server containers start and `docker compose ps` shows all three as `healthy` within the documented 90–120 s envelope.
- Given the stack is up, when the operator opens `http://localhost:8000` and clicks Log in as `testuser` / `testpassword`, then the J1 OIDC happy-path completes and they land on `/books` with their identity rendered.
- Given the stack is up, when the operator runs `docker compose --profile e2e up -d --wait playwright`, then the `playwright` service is created and the e2e suite runs to completion (or use `just e2e-up` for the canonical invocation).
- Given a fresh clone, when the operator runs `docker compose config`, then no profile warnings appear and the rendered spec shows keycloak + bff + resource-server services (no `playwright` unless `--profile e2e` is added).
- Given the spec changes are committed, when `services/bff/tests` and `services/resource-server/tests` are run (`uv run pytest` from each service dir), then all tests still pass (no source code was edited).

## Spec Change Log

- **2026-05-18 — Step-04 review patches (iteration 1).** Three-layer adversarial review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) on the working-tree diff vs baseline `5f9b0f7`. No `intent_gap` or `bad_spec` findings — spec held. 12 patches applied:
  - **P1–P3** README.md: remaining "default profile" / "dev profile" prose updated to "baseline stack" at lines 12, 26, 165.
  - **P4** architecture.md:1283-1289 — dev workflow block updated from `docker compose --profile dev up` to bare `docker compose up`.
  - **P5** docs/security-review.md:82 — "dev profile" → "local baseline stack" in cookie-Secure attestation row.
  - **P6** docs/smoke-run.md — forward-looking sections (Prerequisites, Known setup workarounds, Checklist) updated; historical Run Record + transcript preserved verbatim with a "frozen at fb751ec" banner; D140/D141 marked CLOSED, D142 remains LIVE.
  - **P7** Justfile preamble refreshed to reflect that only the `e2e` profile remains.
  - **P8** deferred-work.md — D140 and D141 closed with Resolution lines pointing at baseline `5f9b0f7`; D142 entry updated to point at `compose/app.yml` (file references to deleted templates retired).
  - **P9–P10** services/bff/src/bff/core/config.py:218 + services/resource-server/src/resource_server/core/config.py:135 — fail-fast error messages updated to stop pointing at retired per-service `.env` files. *Deviation from the spec's Never "Do NOT touch BFF or RS source code" rule, scoped narrowly to text-only edits of operator-facing error strings that referenced deleted files; no behavior change, BFF/RS tests still green.*
  - **P11** services/resource-server/src/resource_server/api/test_reset.py:17 — docstring reference to retired template updated to root `.env.example`. Same narrow text-only deviation as P9/P10.
  - **KEEP — the new compose model.** The retired `default`/`dev` profile names + single-root-`.env` consolidation is load-bearing; the 12 patches are downstream reference-rot fixes, not architecture changes. Re-derivation must preserve: (a) bare `docker compose up` brings up the baseline (Keycloak + BFF + RS); (b) only `e2e` profile remains; (c) `env_file: ../.env` on bff + RS; (d) per-service `environment:` blocks carry topology constants including the BFF-vs-RS `OIDC_ISSUER_URL` split.
  - Findings classified as **defer** or **reject**: pre-existing `compose v5.1.3` references in unchanged comments (defer — out of scope); pre-existing fail-fast guard absences on root `.env` interpolations (reject); TEST_RESET_TOKEN leaking into baseline container envs via `env_file` (reject — local-only project, route stays unmounted on baseline); OIDC_AUTHORIZE_URL_BROWSER no longer in `.env.example` as an operator knob (reject — PRD scope is local-docker only); historical planning docs (sprint-change-proposal, epic-N-retro, epics.md) left unchanged (defer — historical record).

## Design Notes

The crux is that `OIDC_ISSUER_URL` has two correct values depending on consumer:

- **BFF** uses it as a back-channel base URL for Authlib's token exchange against Keycloak — needs `http://keycloak:8080/realms/bmad-books` (compose DNS).
- **RS** uses it as the expected `iss` string when validating JWT signatures — needs `http://localhost:8080/realms/bmad-books` (matches `KC_HOSTNAME=localhost` that Keycloak signs into tokens).

Today the two values are smuggled in via separate per-service `.env` files. The cleaner home for them is `compose/app.yml`'s per-service `environment:` blocks — they are topology constants, not operator-tunable. Root `.env` keeps only what an operator actually edits.

The retirement of `default` and `dev` profiles is safe because they produce *identical containers* today — the operator-side "dev" workflow is `docker compose up` + `cd spa && npm start` (which doesn't need a separate compose profile). Only the `e2e` profile adds a real container (`playwright`); it stays.

Golden example — the new `bff` service block in `compose/app.yml`:

```yaml
bff:
  build: { context: .., dockerfile: services/bff/Dockerfile }
  container_name: bff
  env_file: [../.env]
  environment:
    APP_NAME: bff
    DEBUG: "false"
    BFF_DATABASE_URL: sqlite+aiosqlite:////data/bff.db
    BFF_BASE_URL: http://localhost:8000
    RS_BASE_URL: http://resource-server:8000
    OIDC_ISSUER_URL: http://keycloak:8080/realms/bmad-books  # back-channel
    OIDC_JWKS_URL: http://keycloak:8080/realms/bmad-books/protocol/openid-connect/certs
    OIDC_AUDIENCE: bmad-books-resource-server
    OIDC_CLIENT_ID: bmad-books-bff
    OIDC_AUTHORIZE_URL_BROWSER: http://localhost:8080/realms/bmad-books
    BFF_SESSION_COOKIE_NAME: bff_session
    BFF_CSRF_COOKIE_NAME: csrf_token
  ports: ["8000:8000"]
  # …healthcheck, depends_on, volumes unchanged
```

The RS block mirrors this with its own `OIDC_ISSUER_URL=http://localhost:8080/...` and no BFF-specific cookie env.

## Verification

**Commands:**
- `docker compose config` -- expected: no profile warnings; rendered spec lists keycloak + bff + resource-server only.
- `docker compose --profile e2e config` -- expected: rendered spec adds the `playwright` service; no warnings.
- `docker compose up -d --wait` -- expected: all three services reach `healthy`.
- `docker compose ps` -- expected: keycloak, bff, resource-server all in state `Up (healthy)`.
- `curl -fsS http://localhost:8000/health` -- expected: HTTP 200.
- `curl -fsS http://localhost:9000/health/ready` -- expected: HTTP 200 (Keycloak management endpoint).
- `just e2e-up` -- expected: playwright runner executes the 26-spec suite; all journeys pass.
- `cd services/bff && uv run pytest -q` -- expected: full BFF test suite still green.
- `cd services/resource-server && uv run pytest -q` -- expected: full RS test suite still green.

**Manual checks:**
- Open `http://localhost:8000` in a browser; click Log in as `testuser` / `testpassword`; land on `/books` with identity rendered top-right (J1 happy path).
- Click Log out; verify redirect to `/login`; refresh — verify you stay logged out (J5 happy path).

## Suggested Review Order

**Compose profile retirement (D140)**

- Entry point — service blocks dropped `profiles:`, baseline becomes unconditional
  [`app.yml:57`](../../compose/app.yml#L57)

- Keycloak joins the unconditional baseline
  [`infra.yml:8`](../../compose/infra.yml#L8)

- New profile model documented at the top of the compose entry point
  [`docker-compose.yml:1`](../../../docker-compose.yml#L1)

- E2e overlay header acknowledges retired-profile cleanup but stays functionally untouched
  [`app.e2e.yml:1`](../../compose/app.e2e.yml#L1)

**Env file consolidation (D141)**

- BFF `env_file: ../.env` + topology constants moved into the service's `environment:` block
  [`app.yml:34`](../../compose/app.yml#L34)

- RS mirrors the BFF pattern with its own host-facing `OIDC_ISSUER_URL`
  [`app.yml:117`](../../compose/app.yml#L117)

- Root `.env.example` trimmed to operator-edited values (header rewrite explains the split)
  [`.env.example:1`](../../../.env.example#L1)

**Documentation alignment**

- README setup steps + dev/prod workflows updated for the new baseline-stack model
  [`README.md:19`](../../../README.md#L19)

- Architecture dev workflow snippet drops `--profile dev`
  [`architecture.md:1283`](../../planning-artifacts/architecture.md#L1283)

- Security review cookie-Secure attestation row de-references the retired dev profile
  [`security-review.md:82`](../../../docs/security-review.md#L82)

- Smoke run instructions updated; Run Record preserved verbatim with a "frozen at fb751ec" banner
  [`smoke-run.md:18`](../../../docs/smoke-run.md#L18)

**Justfile + operator-facing error messages**

- Justfile preamble + `default-config` → `config` recipe rename
  [`Justfile:1`](../../../Justfile#L1)

- BFF fail-fast message no longer points at the deleted `services/bff/.env`
  [`config.py:218`](../../../services/bff/src/bff/core/config.py#L218)

- RS fail-fast message points at compose/app.yml instead of the deleted RS template
  [`config.py:135`](../../../services/resource-server/src/resource_server/core/config.py#L135)

- RS test_reset docstring redirected to root `.env.example`
  [`test_reset.py:17`](../../../services/resource-server/src/resource_server/api/test_reset.py#L17)

**Deferred-work tracker**

- D140 and D141 closed with Resolution lines pointing at baseline `5f9b0f7`; D142 entry updated
  [`deferred-work.md:774`](../deferred-work.md#L774)
