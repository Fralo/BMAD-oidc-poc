---
status: done
story_key: 6-2-spa-dockerfile-compose-service-keycloak-realm-port
epic: 6
prerequisites: Story 6.1 (SPA Angular SSR scaffold + Express proxy + cookie-forwarding interceptors) is `review` and has produced a working `spa/src/server.ts` that listens on `PORT` (default `4000`), serves `/_health`, reverse-proxies `/auth/*` `/api/*` `/v1/*` to `BFF_INTERNAL_URL`, and SSR-renders the Angular shell. Story 1.14's SPA-in-BFF surface (BFF Dockerfile Node-builder stage, `services/bff/src/bff/main.py:_register_spa`, `services/bff/tests/api/test_static.py`) is **still live** at 6.2 close — Story 6.3 owns its removal. Source-of-truth for Epic 6 scope is `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.2; Epic 6 is NOT yet in `_bmad-output/planning-artifacts/epics.md` (Story 6.4 owns that edit).
supersedes_partially: Story 1.14 (partial — the BFF's host-port mapping moves to the SPA edge here; the BFF's static-serve code path stays live until Story 6.3 deletes it).
created: 2026-05-19
baseline_commit: ed34ac7
---

# Story 6.2: SPA — Dockerfile + compose service + Keycloak realm port pin

Status: done

<!-- Sprint: Epic 6 (Frontend Split & SSR Edge). Second story in Epic 6. -->
<!-- Follows: Story 6.1 (Angular SSR scaffold + cookie forwarding). -->
<!-- Precedes: Story 6.3 (BFF cleanup — supersede Story 1.14). -->
<!-- Source of truth: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.2 + §2.5 Compose / Docker / Keycloak impact. -->

## Story

As the compose topology,
I want the Angular SSR Express server (built in Story 6.1) packaged as its own `spa` service, taking the host-facing port (`:4000` by default), while the BFF loses its host port and Keycloak's realm registers the new redirect URI,
so that the browser only ever talks to the SPA edge (preserving same-origin), the BFF becomes API-only on the compose network, and `docker compose up` on a fresh clone completes the J1 happy path end-to-end against `http://localhost:4000`.

## Scope (read this first)

Story 6.2 owns the **compose + container + realm port** half of the split. Story 6.1 produced the SSR runtime (`spa/src/server.ts`, the two SSR interceptors, the `app.config.server.ts` provider tree); Story 6.2 wraps that runtime in a Docker image, adds it to compose as a first-class service, flips the BFF's host-port over to the SPA edge, and updates Keycloak's realm so OAuth completes against the new origin.

**Deliverables:**

1. **`spa/Dockerfile`** (NEW) — Node multi-stage build: deps → build → runtime. Runtime stage runs `node dist/spa/server/server.mjs` as a non-root user on `:4000`, with a Node-based healthcheck against `/_health`.
2. **`spa/.dockerignore`** (NEW) — keeps `node_modules`, `dist`, `coverage`, `.angular`, IDE cruft, and VCS artefacts out of the build context.
3. **`compose/app.yml` — new `spa` service block** + **BFF service edits**:
   - `spa`: builds from `../spa/Dockerfile`, publishes `${SPA_HOST_PORT:-4000}:4000`, depends on `bff: service_healthy`, healthcheck on `/_health`, env `BFF_INTERNAL_URL: http://bff:8000` + `SPA_PUBLIC_ORIGIN: http://localhost:${SPA_HOST_PORT:-4000}`.
   - `bff`: drop `ports: ["8000:8000"]`; flip `BFF_BASE_URL: http://localhost:8000` → `BFF_BASE_URL: http://localhost:${SPA_HOST_PORT:-4000}` (browser-facing); update the stale "no separate spa service" comment.
4. **`compose/infra.yml` — Keycloak service env**: add `SPA_HOST_PORT: ${SPA_HOST_PORT:-4000}` so the realm-import substitution at boot picks it up.
5. **`keycloak/realm-bmad-books.json`** — replace the three `http://localhost:8000` occurrences with `http://localhost:${SPA_HOST_PORT:4000}` placeholders (Keycloak / Quarkus MicroProfile substitution; NOTE the bare `:` not `:-`).
6. **`.env.example`** — document the optional `SPA_HOST_PORT` override.
7. **`docker-compose.yml`** — refresh the header comment that currently advertises "SPA bundle baked into the BFF image (Story 1.14)" so it reflects the post-6.2 topology (BFF is API-only; SPA edge owns the browser-facing port). Story 6.3 will refresh again when the BFF's static-serve code goes away.

What this story **does NOT do** (handled by other Epic 6 stories — do not touch any of these here):

- **`services/bff/Dockerfile`** — keep the Stage 0 Node builder. Story 6.3 deletes it.
- **`services/bff/src/bff/main.py`** — keep `_SPA_DIR`, `_register_spa`, the `StaticFiles` import, the `FileResponse` catch-all. Story 6.3 removes them.
- **`services/bff/tests/api/test_static.py`** — keep. Story 6.3 deletes.
- **`services/bff/src/bff/middleware/security_headers.py`** — keep. The CSP middleware moves to `spa/server.ts` (or a sibling file) in Story 6.4 (per Sprint Change Proposal §2.3 A8). Story 6.2 does NOT add CSP to the SPA edge. The browser will receive uncapped HTML from the SPA between 6.2 close and 6.4 close — this is an intentional, documented temporary state for a local-only educational demo.
- **`spa/src/server.ts`** — 6.1 owns it. Do not edit the proxy mount, the `/_health` route, or the Angular handler. (One narrow exception: if AC2 verification reveals the server is unreachable from inside the container — e.g., binding `127.0.0.1` instead of `0.0.0.0` — surface in Anomalies and route the fix back through 6.1 rather than patching it in 6.2.)
- **`spa/src/app/**`** — 6.1 owns all SPA TypeScript.
- **`spa/angular.json`, `spa/tsconfig.app.json`, `spa/package.json`** — 6.1's edits stand. Do not bump dependencies, change build targets, or modify scripts.
- **`compose/app.e2e.yml`** — leave the e2e overlay's `E2E_BASE_URL` and `--host-resolver-rules` references at `:8000`. Story 6.4 sweeps the e2e config; until then the e2e profile may fail (acceptable — 6.2's close-gate is the `default`-stack J1 happy path manually via the browser, not `just e2e-up`).
- **`e2e/playwright.config.ts`** — Story 6.4 owns it.
- **`README.md`, `docs/smoke-run.md`, `docs/security-review.md`, `docs/coverage-report.md`** — Story 6.4 owns all docs.
- **`_bmad-output/planning-artifacts/architecture.md`, `PRD.md`, `epics.md`** — Story 6.4 owns the F3/I6/A8 edits, F7/I9 inserts, the §6 PRD clarification, and the Epic-6 epics.md block.
- **The `Justfile`** — `just e2e-up` runs the e2e profile, which 6.4 will sweep; do not add a `just spa-up` recipe in 6.2 unless verification needs a one-liner (and even then, prefer raw `docker compose up`).

Why this strict scope split: Stories 6.1 and 6.3 each have their own review surface (SPA SSR readiness; BFF cleanup). 6.2's review surface is "compose can stand up the full split topology and the OAuth happy path works against the new port." Folding 6.3's BFF cleanup into 6.2 would create a multi-service diff that's hard to roll back if Keycloak's realm-import substitution surprises us; folding 6.4's docs into 6.2 buries the compose surgery under noise.

## Acceptance Criteria

> Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.2 (AC1–AC8 there). Re-derived here with concrete file paths, exact env-var names verified against the current `compose/app.yml` / `compose/infra.yml` / `keycloak/realm-bmad-books.json`, and live-verification probes adapted from Story 6.1 AC12.

### AC1 — `spa/Dockerfile` builds clean from the SPA build context

**Given** a fresh checkout of `spa/` containing the Story 6.1 outputs (`src/server.ts`, `src/main.server.ts`, `src/app/app.config.server.ts`, `src/app/app.routes.server.ts`),
**When** the developer runs `docker compose build spa` from the repo root,
**Then** the build succeeds and produces an image tagged for the `spa` compose service that:

- Uses `node:22-slim` (LTS; matches Angular CLI 21's engine range, mirrors `services/bff/Dockerfile`'s Stage 0 baseline).
- Has three stages: `deps` (`npm ci`), `build` (`npm run build`), `runtime` (final image).
- Runtime stage carries ONLY `dist/spa/` from the build stage. No `node_modules` — `@angular/build:application` bundles all SSR dependencies (Express, `http-proxy-middleware`, `@angular/ssr/node`) into `dist/spa/server/server.mjs` and `dist/spa/server/main.server.mjs`. Verify this assumption with `docker run --rm --entrypoint sh <image> -c "ls /app && du -sh /app/dist/spa/server"` before closing AC1.
- Runtime stage runs as a non-root `app` user (mirror `services/bff/Dockerfile` Stage 2 lines 45–46 / 65: `groupadd --system app && useradd --system --gid app app`; `USER app`).
- Declares `EXPOSE 4000`, `ENV NODE_ENV=production PORT=4000`, and `ENTRYPOINT ["node", "dist/spa/server/server.mjs"]`.
- Declares a `HEALTHCHECK` that probes `http://localhost:4000/_health` via Node's built-in global `fetch` (Node 22 has it; no `curl`/`wget` package install needed, mirroring `services/bff/Dockerfile:72–75`'s stdlib-only Python probe). One acceptable form:
  ```dockerfile
  HEALTHCHECK --interval=10s --timeout=5s --retries=12 --start-period=15s \
      CMD node -e "fetch('http://localhost:4000/_health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
  ```

**And** `spa/.dockerignore` (NEW) excludes at minimum:
- `node_modules` (the build stage `npm ci`s its own; sending the host's wastes build context bandwidth).
- `dist` (build output; rebuilt in-stage).
- `coverage` (Vitest artefacts).
- `.angular` (Angular CLI cache).
- `*.log`, `npm-debug.log*`.
- `.git`, `.gitignore` (the SPA's build context is `../spa`, not the repo root; nothing should leak in but keep the safety net).
- `.vscode`, `.idea`, `.DS_Store`.

> **Verification commands** (Task 9 will execute):
> - `docker compose build spa` → exits 0.
> - `docker inspect $(docker compose images --quiet spa) --format '{{json .Config.ExposedPorts}}'` contains `"4000/tcp"`.
> - `docker inspect $(docker compose images --quiet spa) --format '{{.Config.User}}'` returns `app` (non-empty, non-root).
> - `docker inspect $(docker compose images --quiet spa) --format '{{json .Config.Healthcheck.Test}}'` is non-null.
>
> **Failure-prevention note (image size):** If the runtime image is >300 MB, something larger than `dist/spa/` got copied in. Audit `COPY` lines and check that `node_modules` is not present in the runtime stage. Story 6.1's build emits ~700 KB across `dist/spa/server` and ~256 KB initial across `dist/spa/browser` — a healthy runtime image is ~200–250 MB (mostly `node:22-slim`'s base layers).

### AC2 — `docker compose up` brings up Keycloak + BFF + RS + SPA, all healthy

**Given** a fresh repo with no images cached AND a `.env` populated from `.env.example` (with `BFF_CLIENT_SECRET` and `TEST_RESET_TOKEN` set to non-placeholder values),
**When** the developer runs `docker compose down -v && docker compose up -d --wait` from the repo root,
**Then** all four services reach the healthy state within 120s:

- `docker compose ps --format json` shows `keycloak`, `bff`, `resource-server`, `spa` all with `"State":"running"` and `"Health":"healthy"`.
- `--wait` exits 0 (it polls compose healthchecks until all services are healthy or 60s default; bump via `--wait-timeout 120` if needed on slower CI).
- The SPA's healthcheck (`node -e ... /_health`) flips green within `start_period=30s` + a few `interval=10s` ticks.
- The compose ordering is enforced by `depends_on: { bff: { condition: service_healthy } }` on the SPA service. The SPA does NOT depend on Keycloak directly — the BFF already does, and the SPA only needs the BFF reachable to start serving.

> **Failure-prevention note 1 (volume realm-import gotcha):** Existing Keycloak volume = no realm re-import. Story 6.2 changes the realm JSON, so the operator MUST `down -v` (or otherwise clear the Keycloak data volume) before the new realm takes effect. AC2 wording uses `down -v` explicitly. The Sprint Change Proposal §2.9 risk row 3 documents this; surface the same step in the story's Completion Notes and again in AC6.
>
> **Failure-prevention note 2 (BFF host port no longer published):** Operators who type `curl http://localhost:8000/...` will get `connection refused` after this story. That's expected — AC5 is the explicit close-gate that verifies it. Make sure no developer-internal documentation or one-liner still references `localhost:8000` for browser-side probes; the in-compose-network address `http://bff:8000` still works.

### AC3 — `curl http://localhost:4000/` returns the SSR-rendered SPA shell

**Given** the stack from AC2 is healthy,
**When** the developer runs `curl -sS -L http://localhost:4000/ | head -c 8000`,
**Then** the response is HTTP 200 (after following the auth-guard redirect chain), `Content-Type: text/html`, and the body contains:

- The literal substring `<app-root` (the Angular host element).
- A hydration attribute on `<app-root>` — `ngh="..."` AND `ng-server-context="ssr"` — proving the SSR Express server (Story 6.1's `server.ts`) handled the render, not a static-served `index.csr.html`.
- A `<script id="ng-state"` element (the transfer-state payload).

The initial GET of `/` will likely 302 to `/login?return_to=%2Fbooks` via Angular Router's auth-guard chain — that's correct (matches Story 6.1 AC12 Probe 1's documented post-implementation behavior at `_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md:691–697`). `curl -L` follows the redirects; the final 200 is what AC3 asserts on.

> **Failure-prevention note 1:** If the response is HTML but no `ngh` / `ng-server-context` markers — the SSR Express server is serving the `index.csr.html` static fallback instead of running the Angular handler. This means the middleware order in `server.ts` is wrong (Angular handler is unreachable) or `outputMode: "server"` regressed in `angular.json`. Do NOT patch `server.ts` from 6.2 — surface in Anomalies and route back through 6.1.
>
> **Failure-prevention note 2:** If the response is `connection refused` — the SPA container is healthy at compose-level but bound to `127.0.0.1` inside the container instead of `0.0.0.0`. Express's default `app.listen(port)` binds to all interfaces on Node 22 — so this would indicate a custom bind in `server.ts`. Surface and route back through 6.1.
>
> **Failure-prevention note 3:** The `allowedHosts: ["localhost"]` setting in `spa/angular.json` (added by Story 6.1) extracts hostname-only (port stripped) — so it covers `localhost:4000`, `localhost:8080`, etc. Inside the compose network, the Express handler receives `Host: spa:4000` (or `Host: localhost:4000` depending on routing). Verify the SSR handler does NOT 400 on `Host: spa:4000` — if it does, add `"spa"` to `allowedHosts` (the schematic-emitted hostname-only check). This is the most likely AC3 failure mode after Story 6.1's setup.

### AC4 — `curl http://localhost:4000/api/me` returns the BFF's 401 envelope (anonymous)

**Given** the stack from AC2 is healthy AND no session cookie is present,
**When** the developer runs `curl -sS http://localhost:4000/api/me`,
**Then** the response is HTTP 401 with body byte-for-byte equal to:

```json
{"errorCode":"session_expired","message":"Session expired or not present","detail":null}
```

This proves the SSR Express proxy (Story 6.1's `http-proxy-middleware` mount) forwards `/api/me` from the SPA edge to the BFF (`http://bff:8000`) intact. The envelope matches the BFF's `/api/me` anonymous response verbatim — see Story 6.1 AC12 Probe 2 (`6-1-...md:700–702`) and `docs/smoke-run.md` 2026-05-18 Run Record.

> **Failure-prevention note 1:** If the response is HTML — middleware order regression (see AC3 note 1).
>
> **Failure-prevention note 2:** If the response is a 502 / 503 / `connection refused` — the SPA container can't reach the BFF on the compose network. Verify with `docker compose exec spa node -e "fetch('http://bff:8000/api/me').then(r => r.text()).then(t => console.log(r.status, t))"` (if Node 22's CLI supports the chain) or `docker compose exec spa wget -qO- http://bff:8000/api/me` if wget is in the slim image. Check `BFF_INTERNAL_URL` env on the SPA service matches `http://bff:8000`. Confirm `bff` service is healthy and on the same compose network (default compose network is shared by all services in a file).
>
> **Failure-prevention note 3:** If the response is the OLD `1.14`-shape SPA `index.html` — the BFF's static-serve mount is intercepting `/api/me`. This means `/api/me` got proxied to the BFF correctly BUT the proxy's path is wrong (e.g., it sent `/me` and the BFF's catch-all served `index.html`). The Story 6.1 fix in `server.ts` is to NOT use `app.use(path, middleware)` (which strips the mount path) but rather mount with `pathFilter`. Confirm `spa/src/server.ts:42–49` matches Story 6.1's landed shape. If it does, the failure is elsewhere — surface and route back through 6.1.

### AC5 — `curl http://localhost:8000/` is unreachable from the host

**Given** the stack from AC2 is healthy,
**When** the developer runs `curl -sS --max-time 5 http://localhost:8000/`,
**Then** the curl exit status is non-zero AND stderr contains `Connection refused` (or `Couldn't connect to server` on some libcurl builds).

This proves the BFF lost its host-port mapping in `compose/app.yml` (the `ports: ["8000:8000"]` block was deleted in this story).

**And** the BFF is still reachable on the compose network from other services:

```
docker compose exec spa node -e "fetch('http://bff:8000/health').then(r => r.text()).then(console.log)"
```

returns `{"status":"ok"}` (or the BFF's health envelope shape; verify against `services/bff/src/bff/api/health.py`).

> **Failure-prevention note:** Do NOT change `BFF_BASE_URL` to `http://bff:8000`. The BFF uses `BFF_BASE_URL` to construct the **browser-facing** OAuth `redirect_uri` (`services/bff/src/bff/api/auth.py:149, 232` — both lines emit `f"{cfg.bff_base_url}/auth/callback"`). The browser sees that URL in Keycloak's `Location` header on the `/auth/login` 302, then navigates to it directly — so it must be browser-reachable (`http://localhost:${SPA_HOST_PORT:-4000}`). The compose-DNS URL `http://bff:8000` is what the SPA's PROXY uses (set via `BFF_INTERNAL_URL` on the SPA service), not what the BFF emits in OAuth response URLs.

### AC6 — `down -v && up` then OAuth happy path completes against `testuser/testpassword`

**Given** the realm-JSON edits in this story have changed `redirectUris`, `post.logout.redirect.uris`, and `webOrigins` from `http://localhost:8000` to `http://localhost:${SPA_HOST_PORT:4000}` (literal placeholder text — Keycloak substitutes at boot),
**And** Keycloak only re-imports the realm if its data volume is empty (the `start-dev --import-realm` mode in `keycloak/Dockerfile:27` does NOT overwrite an existing realm),
**When** the developer runs `docker compose down -v && docker compose up -d --wait`,
**Then** opening `http://localhost:4000/` in a browser produces:

1. The SPA login page (after the auth-guard redirect chain).
2. Clicking the "Sign in" link (or whatever the LoginView's call-to-action is) follows `GET /auth/login` through the SPA proxy to the BFF, which 302s the browser to Keycloak at `http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth?...&redirect_uri=http%3A%2F%2Flocalhost%3A${SPA_HOST_PORT:-4000}%2Fauth%2Fcallback&...`. The decoded `redirect_uri` is now `http://localhost:4000/auth/callback` (it was `http://localhost:8000/auth/callback` before this story).
3. Logging in as `testuser/testpassword` at Keycloak completes; Keycloak 302s the browser back to `http://localhost:4000/auth/callback?code=...&state=...`.
4. The browser hits the SPA edge on `:4000`, which proxies `/auth/callback` to the BFF; the BFF exchanges the code, sets the `bff_session` and `csrf_token` cookies (`Domain=localhost; Path=/`), and 302s back to the SPA route (e.g., `/books` or `return_to`).
5. The browser follows the redirect; the SPA renders `/books` with the user's session active (the `/api/me` call inside `provideAppInitializer` succeeds via the cookie-forward + URL-rewrite SSR interceptors from Story 6.1).
6. The TopChrome shows the logged-in state per UX spec.

**Record in Completion Notes** (Dev Agent Record):
- The exact `Location` header of the `GET /auth/login` 302 (decoded `redirect_uri` query param).
- Any cookies set by the BFF on the `/auth/callback` redirect response (extract from the browser DevTools Network panel — captures `bff_session`, `csrf_token`, and the auth-state cookie).
- The final rendered URL after step 6 (proves the post-login navigation reached `/books`).
- Logout flow — clicking the Logout control completes the BFF's revoke + end-session + clear-cookie chain. After logout, the user lands on `/login` and `/api/me` returns 401 again.

> **Failure-prevention note 1 (realm placeholder syntax):** Keycloak / Quarkus MicroProfile substitution uses `${VAR:default}` with a **bare colon** as the default separator (`${SPA_HOST_PORT:4000}`), NOT `${VAR:-default}` (bash-style — that becomes the literal text `http://localhost:-4000/auth/callback` and OAuth breaks with `Invalid parameter: redirect_uri`). The existing `"secret": "${BFF_CLIENT_SECRET}"` line in the realm JSON proves substitution works; this story extends the same syntax to the three URL lines.
>
> **Failure-prevention note 2 (CSRF Origin check):** The BFF's `CsrfMiddleware` (Story 1.6) compares the request's `Origin` header against `settings.bff_base_url` (see `services/bff/src/bff/auth/csrf.py:102`). After this story `bff_base_url=http://localhost:4000`. The browser sends `Origin: http://localhost:4000` to the SPA edge; `http-proxy-middleware` v3's default behavior forwards the `Origin` header unchanged to the BFF. The check therefore passes. If a state-changing call (POST/PUT/PATCH/DELETE) from the SPA returns 403 `csrf_invalid` post-login, this is the first thing to check — the symptom would be J2 add-book failing right after the J1 happy path completes.
>
> **Failure-prevention note 3 (Set-Cookie domain):** The BFF sets `bff_session` with `Domain=localhost` (or no Domain attribute — browser defaults to the request hostname). When the BFF responds via the SPA proxy, the response goes back through `http-proxy-middleware` and out to the browser unchanged. The browser sees the cookie set with the right Domain because the response URL is `http://localhost:4000/auth/callback` from the browser's perspective. Both `:4000` (SPA) and `:8000` (BFF, internal-only post-6.2) on `localhost` share the same cookie domain — but the browser never connects to `:8000` anymore, so the cookie is effectively scoped to `:4000` traffic.

### AC7 — `SPA_HOST_PORT=4100 docker compose up` brings the SPA up on `:4100` honored end-to-end

**Given** the operator wants to run the stack on a non-default SPA host port (e.g., to avoid a conflict with another service on `:4000`),
**When** they run `SPA_HOST_PORT=4100 docker compose down -v` then `SPA_HOST_PORT=4100 docker compose up -d --wait`,
**Then**:

- `docker compose ps spa` shows the port mapping `0.0.0.0:4100->4000/tcp`.
- `curl http://localhost:4100/` returns the SSR-rendered SPA shell (same shape as AC3, different port).
- `curl http://localhost:4100/api/me` returns the BFF 401 envelope (same shape as AC4).
- The Keycloak realm's `redirectUris` (post-substitution) is `http://localhost:4100/auth/callback`. Verify by hitting `GET /auth/login` on the SPA and inspecting the 302 Location's `redirect_uri` query param — it must contain `localhost%3A4100` (URL-encoded).
- The OAuth happy path from AC6 completes against `http://localhost:4100`.

> **Failure-prevention note:** All three substitution sites must use the env var. Missing one yields a port-mismatch error at OAuth callback time. The three sites:
> 1. `compose/app.yml` SPA service `ports: ["${SPA_HOST_PORT:-4000}:4000"]` — host publish.
> 2. `compose/app.yml` BFF service `BFF_BASE_URL: http://localhost:${SPA_HOST_PORT:-4000}` — OAuth redirect_uri construction.
> 3. `compose/app.yml` SPA service `SPA_PUBLIC_ORIGIN: http://localhost:${SPA_HOST_PORT:-4000}` — `HTTP_TRANSFER_CACHE_ORIGIN_MAP` browser-side key alignment (Story 6.1 `app.config.server.ts:13`).
> 4. `compose/infra.yml` Keycloak service `SPA_HOST_PORT: ${SPA_HOST_PORT:-4000}` — env-pass-through for realm-import substitution.
> 5. `keycloak/realm-bmad-books.json` three `${SPA_HOST_PORT:4000}` occurrences — the actual realm placeholders.
>
> Missing #4 is the silent footgun: the realm JSON keeps placeholders unreplaced and Keycloak boots with literal `http://localhost:${SPA_HOST_PORT:4000}/auth/callback` registered, which fails OAuth with `Invalid parameter: redirect_uri`.

### AC8 — Healthchecks: BFF unchanged, SPA via `/_health`

**Given** the SPA service is defined in `compose/app.yml`,
**When** the developer inspects the `spa` service's `healthcheck:` block,
**Then** it probes `http://localhost:4000/_health` (the route Story 6.1 wired in `spa/src/server.ts:25–27`) via a Node one-liner (mirroring the BFF's stdlib-only Python probe pattern). One acceptable form:

```yaml
healthcheck:
  test: ["CMD", "node", "-e", "fetch('http://localhost:4000/_health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"]
  interval: 10s
  timeout: 5s
  retries: 30
  start_period: 30s
```

**And** the BFF's compose healthcheck block (`compose/app.yml:79–88`) is **unchanged**. The BFF's `python -c "import urllib.request..."` probe still hits `http://localhost:8000/health` (in-container, not host-published), still returns 200. Story 6.2 must not touch the BFF healthcheck — it's load-bearing for the `depends_on: bff: service_healthy` chain that the SPA service relies on.

> **Failure-prevention note 1 (probe binding):** The healthcheck runs INSIDE the SPA container, so `localhost:4000` resolves to the container's loopback — not the host's. Express's default bind on Node 22 covers loopback. The compose-level healthcheck doesn't need `--add-host` magic.
>
> **Failure-prevention note 2 (single-line CMD form):** The single-line `test: ["CMD", "node", "-e", "..."]` form mirrors the BFF healthcheck pattern (Story 1.3 Patch P11 — folded-scalar YAML form is forbidden in this project). Stick to the list-of-strings form to avoid YAML quoting fragility.
>
> **Failure-prevention note 3 (Node 22 `fetch`):** `fetch` is global on Node 22 LTS (since v18 with experimental flag; unflagged in v21+). No `import` needed. Verify with `docker run --rm node:22-slim node -e "console.log(typeof fetch)"` — should print `function`.

### AC9 — Out-of-scope verification (no leaks into 6.1 / 6.3 / 6.4 territory)

**Given** Story 6.2's scope is the compose + container + realm port pin,
**When** the developer runs `git diff --name-only main..HEAD` immediately before closing the story (note: this story lands on `feat/containerization` which already carries Story 6.1's diff; the comparison base is the merge-base with `main`),
**Then** the changed-file list contains **only** files from the following allowlist:

**ALLOWED (this story's deliverables):**
- `spa/Dockerfile` (NEW)
- `spa/.dockerignore` (NEW)
- `compose/app.yml` (MODIFIED — BFF service edits + new `spa` service block)
- `compose/infra.yml` (MODIFIED — Keycloak `SPA_HOST_PORT` env pass-through)
- `keycloak/realm-bmad-books.json` (MODIFIED — three URL-placeholder substitutions)
- `.env.example` (MODIFIED — `SPA_HOST_PORT` documented as an optional override)
- `docker-compose.yml` (MODIFIED — header comment refresh)
- `_bmad-output/implementation-artifacts/6-2-...md` (THIS file — status flips + Tasks/Subtasks/Dev Agent Record)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED — `6-2`: `backlog` → `ready-for-dev` → `in-progress` → `review`)

**ALLOWED IF defers are logged**:
- `_bmad-output/implementation-artifacts/deferred-work.md` (defers from this story, if any — none expected; see Anomalies guidance below).

**SCOPE-LEAK BLOCKLIST (zero entries permitted):**
- `services/bff/Dockerfile` (Story 6.3)
- `services/bff/src/bff/main.py` (Story 6.3)
- `services/bff/tests/api/test_static.py` (Story 6.3)
- `services/bff/src/bff/middleware/security_headers.py` (Story 6.4)
- `services/bff/src/bff/auth/csrf.py` (Story 1.6 — should not need changes; if AC6 verification reveals a CSRF Origin-check failure, surface and route back through investigation rather than editing this file)
- `services/resource-server/**` (no Epic 6 changes touch the RS)
- `spa/src/**` (Story 6.1 owns all SPA TypeScript)
- `spa/angular.json`, `spa/package.json`, `spa/tsconfig.app.json` (Story 6.1)
- `spa/proxy.conf.json` (already deleted in Story 6.1)
- `e2e/**` (Story 6.4)
- `_bmad-output/planning-artifacts/architecture.md`, `PRD.md`, `epics.md` (Story 6.4)
- `_bmad-output/implementation-artifacts/1-14-...md` (Story 6.3 owns the supersession status append)
- `README.md`, `docs/smoke-run.md`, `docs/security-review.md`, `docs/coverage-report.md` (Story 6.4)
- `Justfile` (no new recipes in 6.2 — `just e2e-up` continues to fail until Story 6.4 sweeps the e2e config; this is expected)

**Anomalies** — if AC2–AC8 verification surfaces a real problem that's outside Story 6.2's allowed-touch list (e.g., a missed Story 6.1 detail in `server.ts`, or a BFF code-path issue the proxied flow exposes), record it in Completion Notes under "Anomalies" with a precise file:line citation and route it back through the owning story's review or a new dev-cycle on it. Do NOT patch it in 6.2.

## Tasks / Subtasks

- [x] **Task 1 — Author `spa/Dockerfile`** (AC: 1)
  - [x] 1.1 Stage 0 `deps`: `FROM node:22-slim`, `WORKDIR /spa`, copy `package.json` + `package-lock.json`, run `npm ci --prefer-offline --no-audit --no-fund`.
  - [x] 1.2 Stage 1 `build`: copy `--from=deps` `node_modules`, copy the rest of the SPA source, run `npm run build`. Verify output appears at `/spa/dist/spa/browser` + `/spa/dist/spa/server`.
  - [x] 1.3 Stage 2 `runtime`: `FROM node:22-slim`, create non-root `app` user (mirror `services/bff/Dockerfile:45`), `WORKDIR /app`, copy `--from=build --chown=app:app /spa/dist/spa /app/dist/spa`, `ENV NODE_ENV=production PORT=4000`, `USER app`, `EXPOSE 4000`, `HEALTHCHECK` per AC1 / AC8, `ENTRYPOINT ["node", "dist/spa/server/server.mjs"]`.
  - [x] 1.4 Add a brief file-header comment (mirror the BFF Dockerfile's comment style) naming Story 6.2 + the rationale: SPA SSR edge, `@angular/build:application` bundles deps into the server entry so the runtime image carries no `node_modules`.
  - [x] 1.5 `docker build -t spa-test spa/` standalone from the repo root completes and produces an image. (Smoke; full compose-build is Task 9.)

- [x] **Task 2 — Author `spa/.dockerignore`** (AC: 1)
  - [x] 2.1 Exclude `node_modules`, `dist`, `coverage`, `.angular`, `*.log`, `npm-debug.log*`, `.git`, `.gitignore`, `.vscode`, `.idea`, `.DS_Store`.
  - [x] 2.2 Confirm the build context size with `du -sh spa/` excludes the listed directories conceptually (compose build emits a "Sending build context to Docker daemon" line at the top — verify it's <~5 MB; the live tree is ~250 MB with `node_modules` included).

- [x] **Task 3 — Add `spa` service to `compose/app.yml`** (AC: 1, 2, 7, 8)
  - [x] 3.1 Insert a `spa:` service block AFTER `bff:` and `resource-server:`, BEFORE `playwright:` (or anywhere logical; the `playwright:` block is the e2e profile and should remain last). Match the indentation and field order of the BFF service block for consistency.
  - [x] 3.2 `build: { context: ../spa, dockerfile: Dockerfile }`. Note the relative path: `compose/app.yml` sits at `compose/`, so `../spa` resolves to repo-root `spa/`.
  - [x] 3.3 `container_name: spa` (mirror `bff`, `resource-server` pattern for grep-friendliness).
  - [x] 3.4 `environment:`:
    - `NODE_ENV: production`
    - `PORT: "4000"` (string — compose-env coercion to string is the safe form)
    - `BFF_INTERNAL_URL: http://bff:8000`
    - `SPA_PUBLIC_ORIGIN: http://localhost:${SPA_HOST_PORT:-4000}`
  - [x] 3.5 `ports: ["${SPA_HOST_PORT:-4000}:4000"]`.
  - [x] 3.6 `depends_on: { bff: { condition: service_healthy } }` (NOT keycloak; the BFF already gates on Keycloak, so the SPA gates on BFF transitively).
  - [x] 3.7 `healthcheck:` per AC8 — Node `fetch` one-liner against `/_health`.
  - [x] 3.8 `restart: unless-stopped` (mirror BFF / RS).
  - [x] 3.9 Add a comment header on the service block citing Story 6.2 + the SSR-edge purpose (compress the change-proposal §2.5 SPA section into 4–6 lines, in the same style as the existing BFF / RS service comments at `compose/app.yml:28–34`, `91–107`).

- [x] **Task 4 — Edit `bff:` service in `compose/app.yml`** (AC: 5, 6, 7)
  - [x] 4.1 Delete the `ports: [ "8000:8000" ]` block (currently `compose/app.yml:68–73`). Also delete the surrounding comment about the host port being required for OAuth redirect — the SPA edge now owns that role.
  - [x] 4.2 Change `BFF_BASE_URL: http://localhost:8000` to `BFF_BASE_URL: http://localhost:${SPA_HOST_PORT:-4000}` (line 53). Update the comment block above if it cites the old URL.
  - [x] 4.3 Leave `OIDC_AUTHORIZE_URL_BROWSER`, `OIDC_ISSUER_URL`, `OIDC_JWKS_URL`, `OIDC_AUDIENCE`, `OIDC_CLIENT_ID`, `RS_BASE_URL`, `BFF_DATABASE_URL`, cookie-name fields, and the healthcheck **unchanged**. Especially do NOT change `OIDC_AUTHORIZE_URL_BROWSER` (it's Keycloak's browser-facing URL `http://localhost:8080/...`, not the BFF's).
  - [x] 4.4 Leave `depends_on: { keycloak: service_healthy }` unchanged.
  - [x] 4.5 Update the file-header comment block (`compose/app.yml:1–26`) to note the Story 6.2 split: SPA is now its own service; BFF is internal-only; Story 1.14's static-serve code path is still live (and a future-Story-6.3 cleanup target). Keep the existing D140/D141 and Story 1.12 notes — they're still accurate.

- [x] **Task 5 — Edit `keycloak:` service in `compose/infra.yml`** (AC: 6, 7)
  - [x] 5.1 Add a new line to `keycloak.environment:` block: `SPA_HOST_PORT: ${SPA_HOST_PORT:-4000}`. This makes the env var available to Keycloak's process at startup, where the realm-import substitution can pick it up.
  - [x] 5.2 Update the comment block above the service if needed — note that the realm JSON now substitutes `${SPA_HOST_PORT:4000}` (Keycloak / Quarkus MicroProfile syntax) for the redirect URI host port.
  - [x] 5.3 Do NOT touch `KC_HOSTNAME`, `KC_HOSTNAME_STRICT`, the admin bootstrap vars, the healthcheck, or the ports (`8080`, `9000` stay published; only the BFF's `:8000` port goes away).

- [x] **Task 6 — Edit `keycloak/realm-bmad-books.json`** (AC: 6, 7)
  - [x] 6.1 Line 80 `"post.logout.redirect.uris": "http://localhost:8000/*"` → `"post.logout.redirect.uris": "http://localhost:${SPA_HOST_PORT:4000}/*"`.
  - [x] 6.2 Line 84 `"http://localhost:8000/auth/callback"` (in the `redirectUris` array) → `"http://localhost:${SPA_HOST_PORT:4000}/auth/callback"`.
  - [x] 6.3 Line 87 `"http://localhost:8000"` (in the `webOrigins` array) → `"http://localhost:${SPA_HOST_PORT:4000}"`.
  - [x] 6.4 Verify the bare-colon (`:`) Keycloak default-separator syntax versus the dashed (`:-`) bash-style separator. The existing `"${BFF_CLIENT_SECRET}"` at line 71 has no default; the new placeholders need a default per AC7. Use `${SPA_HOST_PORT:4000}` (bare colon).
  - [x] 6.5 Make NO other changes to the realm JSON. Specifically, do not touch `clientScopes`, `protocolMappers`, the test users, or any other client attributes.

- [x] **Task 7 — Edit `.env.example`** (AC: 7)
  - [x] 7.1 Add a new commented block (after the test-reset section, ~line 33) documenting `SPA_HOST_PORT`:
    ```
    # --- SPA edge host port (optional override) ---------------------------------
    # Default 4000. The Angular SSR edge container publishes this host port to
    # the container's 4000. Affects three substitution sites:
    #   - compose/app.yml SPA service `ports:` + BFF service `BFF_BASE_URL`
    #   - compose/app.yml SPA service `SPA_PUBLIC_ORIGIN`
    #   - keycloak/realm-bmad-books.json redirect/webOrigin URLs
    # Keycloak only re-imports the realm on an empty data volume; after
    # changing this, run `docker compose down -v && docker compose up`.
    #SPA_HOST_PORT=4000
    ```
  - [x] 7.2 Keep the `SPA_HOST_PORT=4000` line commented out — the default works for the documented stack; the operator only un-comments and edits if they need a non-default port.

- [x] **Task 8 — Edit `docker-compose.yml` header comment** (AC: 9 — keep allowed-touch list accurate)
  - [x] 8.1 The current header (lines 1–17) says: `compose/app.yml : BFF, Resource Server (Stories 1.3, 3.1) + SPA bundle baked into the BFF image (Story 1.14)`. After Story 6.2 the SPA is its own compose service. Update the line to read something like: `compose/app.yml : BFF, Resource Server, SPA SSR edge (Stories 1.3, 3.1, 6.2). The BFF's Story-1.14 static-serve code path is still in the BFF image but unreachable from the browser; Story 6.3 removes it.`
  - [x] 8.2 Update the profile-model paragraph (lines 8–14): "dev workflow" no longer involves a host `cd spa && npm start` — the SSR edge is in compose. Replace that line with: `the "dev" workflow is now containerized — bare \`docker compose up\` brings up the full topology including the SPA SSR edge on \`:${SPA_HOST_PORT:-4000}\`. Host-side \`ng serve\` was retired with Story 6.1's deletion of \`spa/proxy.conf.json\`.` (Adapt the wording to fit existing style.)
  - [x] 8.3 Keep the `include:` block unchanged — `compose/app.yml` continues to define `spa` alongside `bff` + `resource-server`; no new include file needed.

- [x] **Task 9 — Live verification** (AC: 1, 2, 3, 4, 5, 6, 7, 8)
  - [x] 9.1 `docker compose down -v` (clear Keycloak volume so the new realm imports).
  - [x] 9.2 `docker compose build` (builds all services; `spa` will rebuild from scratch the first time).
  - [x] 9.3 `docker compose up -d --wait` (start detached; wait for healthchecks; pass `--wait-timeout 120` if 60s isn't enough on first run with cold image pulls). Verify `docker compose ps` shows all four services `running` + `healthy`.
  - [x] 9.4 Run probes against `:4000`:
    - `curl -sS -L -o /tmp/spa-root.html http://localhost:4000/ && grep -c 'ng-server-context="ssr"' /tmp/spa-root.html` → at least 1.
    - `curl -sS -o /tmp/spa-me.json -w '%{http_code}\n' http://localhost:4000/api/me` → `401` and `/tmp/spa-me.json` exactly matches the AC4 envelope.
    - `curl -sS --max-time 5 -o /dev/null -w '%{http_code} %{exitcode_unused}\n' http://localhost:8000/` → curl exit status non-zero (use `echo $?` to confirm).
    - `curl -sS http://localhost:4000/_health` → `{"ok":true}` (200).
  - [x] 9.5 OAuth happy path manually via the browser at `http://localhost:4000`. Record cookies + final URL + logout flow per AC6.
  - [x] 9.6 Bonus CSRF probe: post-login, click an action that fires a state-changing request (e.g., add a book in J2 if available, or POST `/v1/books` via the browser DevTools console) — verify it returns the expected 200/201, NOT a 403 `csrf_invalid`. Confirms the CSRF Origin check is passing against `bff_base_url=http://localhost:4000`.
  - [x] 9.7 `SPA_HOST_PORT=4100 docker compose down -v && SPA_HOST_PORT=4100 docker compose up -d --wait` — re-run probes 9.4 + 9.5 against `:4100` to satisfy AC7. Verify the OAuth `redirect_uri` query param contains `localhost%3A4100`.
  - [x] 9.8 Restore default: `docker compose down -v && docker compose up -d --wait` for the canonical `:4000` stack.

- [x] **Task 10 — Scope-leak audit + close** (AC: 9)
  - [x] 10.1 `git status --short` clean of `services/bff/Dockerfile`, `services/bff/src/`, `services/bff/tests/`, `services/resource-server/`, `spa/src/`, `spa/angular.json`, `spa/package.json`, `spa/tsconfig.app.json`, `e2e/`, `_bmad-output/planning-artifacts/`, `README.md`, `docs/`, `Justfile`.
  - [x] 10.2 Any anomalies discovered in Task 9 that fall outside 6.2's allowed-touch list go into Completion Notes "Anomalies" with a precise file:line citation. Decide: defer-vs-route-back-to-owning-story.
  - [x] 10.3 Status flip: `ready-for-dev → in-progress → review`; update `sprint-status.yaml` `6-2-...: backlog → in-progress → review` per the existing pattern.

### Review Findings (2026-05-19)

Adversarial review pass (Blind Hunter + Edge Case Hunter + Acceptance Auditor) executed against the 7-file 6.2 diff (~351 lines). Acceptance Auditor: 15 PASS / 0 PARTIAL / 0 FAIL / 0 NEW. Blind Hunter raised ~22 issues; Edge Case Hunter raised ~38 paths. After dedup + scope-filtering (most edge-case findings target `spa/src/server.ts` which is Story 6.1's territory and many were already addressed in Story 6.1's review pass via P2/P5/P7), four real patches remain — all scoped to 6.2's deliverable files.

- [x] [Review][Patch] P1 — Healthcheck `.catch` swallows error message [`spa/Dockerfile:69`, `compose/app.yml:208`] — APPLIED: `.catch` now logs `'healthcheck:', e && e.message || e` to stderr before `process.exit(1)`, so `docker inspect <container> --format '{{json .State.Health.Log}}'` surfaces the actual error instead of an opaque "unhealthy".
- [x] [Review][Patch] P2 — `init: true` on `spa` service to fix Node-as-PID-1 SIGTERM [`compose/app.yml` spa service block] — APPLIED: adds Docker's tini-style PID-1 wrapper so `docker stop` / `docker compose down` forwards SIGTERM correctly and reaps zombies. Verified live via `docker inspect spa --format '{{.HostConfig.Init}}'` → `true`. Cheaper than wiring a `process.on('SIGTERM', ...)` handler in `spa/src/server.ts` (Story 6.1's territory; D151 still tracks the in-process variant if it ever becomes desirable).
- [x] [Review][Patch] P3 — Add `.env*` patterns to `spa/.dockerignore` (defense-in-depth against secret leakage) [`spa/.dockerignore`] — APPLIED.
- [x] [Review][Patch] P4 — Add `**/*.spec.ts` to `spa/.dockerignore` (specs aren't bundled into the SSR output) [`spa/.dockerignore`] — APPLIED.
- [x] [Review][Defer] D1 — Build/deps stages run `npm ci` as root (npm postinstall scripts execute as root) [`spa/Dockerfile:18,33`] — deferred, pre-existing pattern across BFF/RS Dockerfiles; cross-cutting hardening belongs in a dedicated security story.
- [x] [Review][Defer] D2 — `SPA_PUBLIC_ORIGIN` and `BFF_BASE_URL` (and the realm JSON URLs) all read from `${SPA_HOST_PORT:-4000}` separately; a YAML anchor would prevent drift [`compose/app.yml:68, 119`] — deferred, cosmetic refactor; current comments document the relationship explicitly.
- [x] [Review][Defer] D3 — `container_name: spa` blocks `docker compose -p <alt> up` for parallel project instances [`compose/app.yml` spa block] — deferred, convention across all four services (`bff`, `keycloak`, `resource-server`, `spa`); changing one without the others creates inconsistency.
- [x] [Review][Defer] D4 — No `mem_limit` / `cpus` resource caps on the SPA container [`compose/app.yml` spa block] — deferred, no other service in the project sets caps; cross-cutting capacity-planning concern.
- [x] [Review][Defer] D5 — `restart: unless-stopped` can mask crashloops in dev (5 minutes of "running" via healthcheck retries before unhealthy) [`compose/app.yml:149`] — deferred, convention across all services; a dev-only override would be the right fix but spans every service.

Notes on dismissed-as-noise (≈50 total, not enumerated): the vast majority were either (a) findings against `spa/src/server.ts` and other `spa/src/**` code that belongs to Story 6.1's review surface — Story 6.1's code-review pass already applied P2 (proxy hardening + 502 handler), P5 (trailing-slash normalization), P7 (Number(PORT) + server.on('error')); (b) speculative concerns about features that don't exist (HTTPS BFF, locales in SSR rendering, native modules in the bundle); (c) project-scope concerns (LAN/CI access, IPv6/IPv4 resolution) excluded by the local-only educational demo posture per PRD §6 and CLAUDE.md memory `BMAD_books scope`; (d) intentional behavior changes that AC2/AC5 explicitly verify (BFF :8000 host port removed); (e) misreadings of compose semantics (compose `${VAR:-default}` correctly handles empty AND unset, so `SPA_HOST_PORT=` empty → defaults to 4000); (f) duplicate forward-looking comment objections — the codebase convention is to cross-reference future stories in comments where it aids navigation.

## Dev Notes

### What this story changes vs. preserves in the topology

**New files** (2):
- `spa/Dockerfile` — three-stage Node multi-stage build.
- `spa/.dockerignore` — keeps the SPA build context tight.

**Modified files** (5 + 2 artefacts):
- `compose/app.yml` — adds `spa:` service block; drops BFF host-port; flips `BFF_BASE_URL`.
- `compose/infra.yml` — adds `SPA_HOST_PORT` env pass-through on Keycloak.
- `keycloak/realm-bmad-books.json` — three `:8000` → `:${SPA_HOST_PORT:4000}` substitutions.
- `.env.example` — documents the optional `SPA_HOST_PORT` override.
- `docker-compose.yml` — refresh the header comment to match the post-6.2 topology.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status flip.
- `_bmad-output/implementation-artifacts/6-2-...md` — THIS file.

**Files NOT to touch** (preserved as-is — see AC9 blocklist for the full list):
- All `services/bff/**` (Story 6.3's territory; the BFF's Story-1.14 static-serve path stays live at 6.2 close).
- All `services/resource-server/**` (zero Epic 6 changes).
- All `spa/src/**` and `spa/angular.json` (Story 6.1's territory).
- All `e2e/**` and `Justfile` (Story 6.4's territory).
- All planning artefacts and docs (Story 6.4's territory).

### Why the SPA build context is `../spa`, not `..` (root)

The BFF Dockerfile (`services/bff/Dockerfile`) uses a repo-root build context (`context: ..` in `compose/app.yml:34`) because Stage 0 needs to copy `spa/` from the sibling directory (Story 1.14's D4 resolution). After Story 6.3, that root context becomes unnecessary; for now it stays.

The SPA Dockerfile has the opposite constraint: it only needs `spa/`. Use `context: ../spa` so the build context is tight (~5 MB after `.dockerignore`) instead of the full repo (~250 MB even with the root `.dockerignore`). Local `.dockerignore` in `spa/` is the only ignore file consulted with this context.

This means `spa/Dockerfile`'s COPY instructions use bare paths (relative to `spa/`):
```dockerfile
COPY package.json package-lock.json ./
COPY . .
```
NOT `COPY spa/package.json ./` — that pattern is for root-context builds (BFF).

### Why no `node_modules` in the runtime image

Angular 21's `@angular/build:application` builder with `outputMode: "server"` bundles every npm import that `server.ts` reaches into `dist/spa/server/main.server.mjs` (446 KB observed in Story 6.1's review build). Express, `http-proxy-middleware`, `@angular/ssr/node`, and every transitive dep get inlined. The Node 22 runtime just needs the language runtime + that file.

Practical confirmation pattern (run during Task 1):
```sh
docker run --rm --entrypoint sh spa-test -c "ls -la /app && du -sh /app/dist/spa && find /app/node_modules 2>/dev/null | head -5"
```
Expected: `/app/dist/spa/` present (~1 MB total); `node_modules` not found (`find` exits 0 with no lines, or 1 with `No such file or directory`).

If the SSR server fails at runtime with `Cannot find module '...'` errors, the bundler MISSED a dep — surface as Anomalies, route to Story 6.1 (the bundler config is in `spa/angular.json`, which 6.1 owns).

### CSP middleware is intentionally NOT in this story

Sprint Change Proposal §2.3 amends decision **A8**: "served via response header from the BFF" → "served via response header from the SPA SSR server". That move is **Story 6.4's** scope. Between Story 6.2 close and Story 6.4 close, HTML responses from the SPA edge carry no CSP header. The BFF's `SecurityHeadersMiddleware` still attaches CSP to its JSON responses (which the SPA edge proxies through unchanged) — but JSON responses don't carry browser-evaluable CSP.

For a local-only educational demo this is acceptable temporary state; do not preempt 6.4 by adding CSP middleware to `spa/src/server.ts` in this story. Note the gap in Completion Notes so 6.4's reviewer sees it explicitly.

### Realm-import substitution mechanics

Keycloak 26's realm import (configured by `start-dev --import-realm` in `keycloak/Dockerfile:27`) reads JSON files from `/opt/keycloak/data/import/` at boot. For each file, Quarkus's MicroProfile Config substitution runs over the JSON text: any `${VAR}` placeholder is replaced with the env value before parsing. The colon-default form is `${VAR:default}` (bare colon).

**Substitution is one-shot at boot.** Once the realm is imported into Keycloak's H2 / persistent DB, subsequent `up` invocations do NOT re-run the import — Keycloak sees the realm already exists. So `SPA_HOST_PORT` changes require `docker compose down -v` (wipes the Keycloak data volume) before they take effect.

The existing `"secret": "${BFF_CLIENT_SECRET}"` at line 71 is proof the substitution mechanism works against this realm. The Story 6.2 additions extend the same pattern to the three URL fields.

**Tested syntax precedent:**
- `${BFF_CLIENT_SECRET}` — works (no default; required).
- `${SPA_HOST_PORT:4000}` — expected to work (Quarkus default-separator is bare `:`).

If `${SPA_HOST_PORT:4000}` substitution fails (Keycloak boots with the literal placeholder in the realm), the symptom is "Invalid parameter: redirect_uri" at OAuth start. Workaround: hardcode the literal port (`http://localhost:4000/...`) and drop AC7 as deferred work. But this is unlikely — the `${VAR:default}` syntax is standard in Quarkus / Keycloak Helm charts / official examples.

### Files-being-modified — current state and what changes

**`compose/app.yml`** (line numbers from the snapshot at baseline commit `ed34ac7`):
- Lines 1–26 — file-header comment. Update to note the Story 6.2 split (Task 4.5 + Task 8 keep the prose accurate).
- Lines 27–89 — `bff:` service block. Modify:
  - Lines 50–67 `environment:` — flip `BFF_BASE_URL` to `http://localhost:${SPA_HOST_PORT:-4000}` (line 53).
  - Lines 68–73 `ports:` — DELETE the entire block (host-port mapping goes away).
  - Lines 74–88 — leave `volumes:`, `depends_on:`, `healthcheck:`, `restart:` unchanged.
- Lines 91–147 — `resource-server:` service block. UNCHANGED (RS has no host port today; nothing to do).
- Lines 149–219 — `playwright:` service block. UNCHANGED (Story 6.4 sweeps e2e).
- Lines 221–229 — volumes. UNCHANGED.
- **Insert the new `spa:` block** between the `resource-server:` block (ends ~147) and the `playwright:` block (starts ~149). The `playwright:` block must stay last in the services dict so the e2e profile semantics are clear.

**`compose/infra.yml`**:
- Lines 17–32 `keycloak.environment:` — add a line `SPA_HOST_PORT: ${SPA_HOST_PORT:-4000}` (Task 5.1). Either at the top of the env block or grouped with `KC_HOSTNAME` (the existing KC_-prefixed lines are Keycloak-config-shape; `SPA_HOST_PORT` is unprefixed — it's only a substitution input for the realm import — so placing it after the `KC_BOOTSTRAP_*` block reads naturally).
- All other lines UNCHANGED.

**`keycloak/realm-bmad-books.json`**:
- Line 80 — `"post.logout.redirect.uris": "http://localhost:8000/*"` → `"post.logout.redirect.uris": "http://localhost:${SPA_HOST_PORT:4000}/*"`.
- Line 84 — `"http://localhost:8000/auth/callback"` → `"http://localhost:${SPA_HOST_PORT:4000}/auth/callback"`.
- Line 87 — `"http://localhost:8000"` (inside `webOrigins`) → `"http://localhost:${SPA_HOST_PORT:4000}"`.
- All other lines UNCHANGED — do NOT touch `clientScopes`, `protocolMappers`, users, or any other client attributes.

**`.env.example`**:
- Append the new SPA_HOST_PORT section (Task 7.1) AFTER the existing test-reset block (current EOF ~line 32).

**`docker-compose.yml`**:
- Refresh lines 1–14 header comment (Task 8.1, 8.2). Keep the `include:` block unchanged.

### Story 6.1 outputs the SPA Dockerfile consumes

Confirmed by reading the Story 6.1 file at `_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md`:

1. **Entry point**: `dist/spa/server/server.mjs` — the SSR Express server (the `ENTRYPOINT` of the runtime stage).
2. **Companion bundles**: `dist/spa/server/main.server.mjs` (Angular server app), `dist/spa/server/angular-app-manifest.mjs`, `dist/spa/server/angular-app-engine-manifest.mjs`, plus chunked `.mjs` files. All needed at runtime — `COPY --from=build /spa/dist/spa /app/dist/spa` captures them all.
3. **Browser bundle**: `dist/spa/browser/main-*.js` + `index.csr.html` + assets. Served by `express.static` within `server.ts` (lines 52–58 of the 6.1-landed file).
4. **Env vars consumed by `server.ts`**:
   - `BFF_INTERNAL_URL` (default `http://localhost:8000`) — the proxy target.
   - `PORT` (default `4000`) — the listen port.
5. **Env vars consumed by `app.config.server.ts`** (`spa/src/app/app.config.server.ts:9, 13`):
   - `BFF_INTERNAL_URL` — provided to `SSR_API_TARGET` injection token.
   - `SPA_PUBLIC_ORIGIN` (default `http://localhost:4000`) — the right-hand side of `HTTP_TRANSFER_CACHE_ORIGIN_MAP`.

The `compose/app.yml` `spa:` service block sets all three via `environment:` (Task 3.4).

### What still works after Story 6.2 closes (regression surface)

- **J1 (login)** — happy path completes via the browser at `http://localhost:4000` (AC6). The BFF + Keycloak + RS continue to function; only the front door moved.
- **J2 (manage books)**, **J3 (estimate)**, **J4 (reading speed)** — assuming the operator logs in via J1 first, the SPA's existing service implementations continue to work because the SPA edge proxies all `/api/*` and `/v1/*` paths through to the BFF unchanged.
- **J5 (logout)** — works (AC6 includes the logout flow).
- **J6 (RS unavailable)** — works in principle; the SPA edge doesn't sit in the BFF↔RS call path. Story 6.4 will re-verify under the e2e profile.
- **`docs/smoke-run.md` historical Run Record** — frozen, untouched, accurate at the snapshot date (2026-05-18). Future Run Records target `:4000` (Story 6.4 owns).
- **The BFF's `/v1/test/reset` endpoint** — works on the compose network. The `playwright` service hits it via `BFF_BASE_URL=http://bff:8000` (line 187 of `compose/app.yml`) which is compose-DNS and doesn't depend on the BFF having a host port.

### What BREAKS after Story 6.2 closes (and that's intentional)

- **`just e2e-up`** — Story 6.4 owns the e2e config sweep. Until then, the Playwright runner's `E2E_BASE_URL: http://localhost:8000` (compose/app.yml:181) targets the BFF, which no longer has a host port — but `--host-resolver-rules` (Story 6.4 work) remaps `localhost:8000 → bff:8000` so the runner can reach it. Once 6.4 lands, that rule will remap to `spa:4000`. In the interim, `just e2e-up` MAY pass on the existing rules (BFF still reachable via DNS) but may fail on URL assertions that expect `:4000`. Either outcome is acceptable for 6.2's close-gate. Do NOT chase a green `just e2e-up` from inside 6.2.
- **Host-side `cd spa && npm start`** — Story 6.1 deleted `spa/proxy.conf.json`, so this dev path is already broken. The containerized SPA edge is the documented dev path post-Epic-6.
- **`curl http://localhost:8000/...`** — connection refused (AC5). All operator-facing probes use `:4000`.

### `http-proxy-middleware` v3 / v4 default behaviors the proxy chain relies on

Story 6.1's `spa/src/server.ts` mounts the proxy with `{ pathFilter: ['/auth', '/api', '/v1'], target: bffInternalUrl, changeOrigin: true, xfwd: true }`. Story 6.2 doesn't change `server.ts`, but the AC6 OAuth verification depends on these proxy-library defaults staying as documented:

- **Header forwarding** — every incoming header (including `Cookie`, `X-CSRF-Token`, `Origin`) is forwarded by default. Critical for AC6 (Cookie roundtrip) and AC6 note 2 (Origin check).
- **Response forwarding** — every response header (including `Set-Cookie`) is forwarded back to the client. Critical for AC6 (the BFF sets `bff_session` and `csrf_token` on the `/auth/callback` 302; the browser must see those Set-Cookie headers).
- **`xfwd: true`** — adds `X-Forwarded-{For,Host,Proto,Port}`. The BFF doesn't currently read these but they're a no-cost good-citizen default and may matter when CSP move + future hardening lands in 6.4.
- **`changeOrigin: true`** — rewrites the outgoing `Host` header to match the target. Required because Express defaults to keeping the inbound `Host` (here `localhost:4000`) but the BFF needs to see `bff:8000` for some internal routing (Authlib's URL construction in particular).

If any of these defaults shift in a future `http-proxy-middleware` version bump, Story 6.2's AC chain may regress. Pin the version in `spa/package.json` to whatever Story 6.1 landed (currently `^4.0.0` per package.json line 26) and do NOT bump in this story.

### Project Structure Notes

- The new `spa/Dockerfile` follows the BFF/RS multi-stage Node/Python pattern — same comment block style, same non-root-user pattern, same single-line healthcheck shape. Consistency makes future operators recognize the topology at a glance.
- The new `spa/.dockerignore` is per-service (build context is `../spa`), unlike the root `.dockerignore` that applies to BFF + RS builds (per Story 1.14's root-context decision). This is the FIRST per-service `.dockerignore` to be live in the project — the BFF + RS ones became dead files when their build contexts went root. Document this in the `.dockerignore` comment header.
- The realm JSON's three placeholder edits all use the SAME variable, all use the SAME default. Symmetry: any future port change is one variable, three substitutions.
- `compose/app.yml`'s service order after this story: `bff`, `resource-server`, `spa`, `playwright`. Keep `playwright` last (e2e-profile convention).

### Previous Story Intelligence

- **Story 6.1** — produced the SSR runtime that this story containerizes. Read `_bmad-output/implementation-artifacts/6-1-...md` lines 542–561 ("Dev-loop reality") and lines 558–561 (the two Angular 21 SSR gotchas: `RenderMode.Prerender` build crash + `allowedHosts` empty array) before starting Task 9 verification. Both gotchas are already resolved in 6.1's landed shape; 6.2 inherits the fixes.
- **Story 1.14** — established the BFF's multi-stage Dockerfile + root build context. Story 6.2's SPA Dockerfile uses a per-service context instead (different constraint set — see "Why the SPA build context is `../spa`" above). Mirror the BFF's stage comments, non-root-user pattern, and healthcheck shape; do not mirror its build context choice.
- **Story 1.2** — established the Keycloak realm-as-code pattern (`keycloak/Dockerfile` bakes the realm JSON at `/opt/keycloak/data/import/`; `start-dev --import-realm` imports at boot). Story 6.2 extends the realm JSON with three `${SPA_HOST_PORT:4000}` placeholders; the import mechanism is unchanged.
- **Story 1.3 / Story 3.1** — established the per-service healthcheck pattern (stdlib-only, single-line CMD form). Story 6.2 mirrors this on the SPA service with a Node `fetch` one-liner.
- **Story 1.5** — established the BFF's reading of `BFF_BASE_URL` for OAuth redirect_uri construction (`services/bff/src/bff/api/auth.py:149, 232`). Story 6.2 flips this env value to the SPA edge URL; the BFF code is unchanged.
- **Story 1.6** — established `CsrfMiddleware`'s Origin check against `settings.bff_base_url` (`services/bff/src/bff/auth/csrf.py:102`). Same env flip propagates; no code change.
- **Story 5.4** — established the smoke-run Run Record format. Story 6.4 will add a new Run Record after 6.2 closes; 6.2 itself does NOT touch `docs/smoke-run.md`.

### Git Intelligence (recent commits on `feat/containerization`)

```
ed34ac7 fix(d140-d141): make bare `docker compose up` work for a fresh clone   (main + feat/containerization HEAD)
5f9b0f7 chore(epic-5): retrospective — flip epic-5 done, A1/A2 action items
b81129a Merge story 5.4 — final docker compose up smoke (default profile)
3d5f0b6 chore(5.4): code review — 8 patches applied, mark done, log D144-D148
417ab1e Merge epic-5 into E5S4 — resolve conflicts + renumber D-IDs
```

- The `feat/containerization` branch is currently at the same SHA as `main` (`ed34ac7`); Story 6.1's work is uncommitted in the working tree (per `git status --short` showing 11 modified/deleted + 8 untracked files under `spa/` + planning artefacts). This means Story 6.2 will likely land on top of an uncommitted 6.1 working tree, OR after 6.1 merges to a branch and 6.2 forks from there. Either way: do NOT include any of the 11+8 = 19 files in the "ALLOWED" list for AC9 — they belong to 6.1's review surface.
- `ed34ac7` (D140/D141) — the single recent compose-related commit. Removed per-service `.env` files; consolidated topology constants into compose `environment:` blocks. Story 6.2 follows this pattern: `BFF_INTERNAL_URL`, `SPA_PUBLIC_ORIGIN`, `NODE_ENV`, `PORT`, and `SPA_HOST_PORT` (Keycloak env pass-through) all live in compose `environment:` blocks, NOT in `.env`. The `.env.example` only documents `SPA_HOST_PORT` as an optional override because it's the one operator-facing tunable.
- No previous Dockerfile work on the SPA side — `spa/Dockerfile` is the first SPA Docker artefact in the repo.

### Latest Tech Information

Verified against current Docker / Compose / Keycloak / Angular docs (May 2026):

- **`node:22-slim`** — Node 22.x LTS (Codename "Jod"), Debian-slim base. Includes `node`, `npm`, but no `curl` / `wget`. Global `fetch` available (no `--experimental-fetch` flag). ~150 MB compressed base layer.
- **Compose `${VAR:-default}` substitution** — shell-style, evaluated at compose-config time (i.e., when `docker compose config` or `docker compose up` runs). The `:-` separator returns the default if the var is unset OR empty.
- **Keycloak / Quarkus `${VAR:default}` substitution** — MicroProfile Config style, evaluated when Keycloak's realm import runs (boot time). The bare `:` separator returns the default if the var is unset (NOT empty — empty is its own value). For our `SPA_HOST_PORT`, "set to empty string" never happens in practice, so this distinction is moot.
- **Compose healthcheck `start_period`** — Compose v2.20+ honors this; older versions interpret it as a deprecated synonym for the first interval. The project pins Compose v2 via the `docker compose` (no hyphen) command in the `Justfile`. `start_period: 30s` is the same value used by the BFF / RS / Keycloak healthchecks for consistency.
- **`http-proxy-middleware` v4** — landed in 2026-05 (Story 6.1 baseline); Story 6.2 does not bump this. v4 dropped the legacy `pathFilter: 'function'` form and tightened error-handling defaults, but `pathFilter: ['/auth', '/api', '/v1']` (array of prefixes) continues to work identically to v3.
- **Angular 21 `@angular/build:application` with `outputMode: "server"`** — bundles all SSR deps into the server entry. The runtime image does NOT need `node_modules`. Verified empirically in Story 6.1's review (`du -sh dist/spa/server` = ~700 KB).
- **`docker compose --wait`** — added in Compose v2.13. Polls all services' healthchecks until they reach `healthy` or `--wait-timeout` seconds elapse (default 60s). The project's existing `just e2e-up` (Justfile:65) uses `--wait` on the e2e profile; Story 6.2 inherits the pattern.

### Testing Standards

- **No new pytest tests in 6.2** — Story 6.2 doesn't touch BFF or RS Python code, so no test changes there. (Story 6.3 will delete `services/bff/tests/api/test_static.py`.)
- **No new Vitest tests in 6.2** — Story 6.2 doesn't touch SPA TypeScript. (Story 6.1 already added the SSR interceptor specs; aggregate sits at 164 specs / 21 files, ≥80% per-file coverage on new code.)
- **Verification IS the test surface for 6.2** — AC2 through AC8 are all live-stack probes against the running compose topology. The smoke-style verification mirrors Story 5.4's pattern (manual operator playthrough) and Story 6.1 AC12 (host-run probes). Record raw probe outputs in Completion Notes under "AC verification probes" with timestamps.
- **No e2e (Playwright) verification in 6.2** — that's Story 6.4's territory. The Playwright runner's `E2E_BASE_URL` and `--host-resolver-rules` are still pointing at `:8000`, which is internal-only after this story. Running `just e2e-up` from inside 6.2 has indeterminate behavior; do not include in the close-gate.

### References

- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §4 Story 6.2 (AC1–AC8) — primary source of truth for Epic 6 Story 6.2 scope]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §2.5 Compose / Docker / Keycloak impact — file-by-file change list]
- [Source: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md` §2.9 Risks — realm volume-import gotcha, OAuth redirect_uri mismatch risk]
- [Source: `_bmad-output/implementation-artifacts/6-1-spa-angular-ssr-scaffold-proxy-cookie-forwarding.md` — the SSR runtime this story containerizes; especially §"Dev-loop reality" + AC12 probe shapes]
- [Source: `_bmad-output/implementation-artifacts/1-14-bff-multi-stage-build-serves-spa-bundle.md` — the BFF multi-stage pattern this story mirrors for the SPA]
- [Source: `_bmad-output/planning-artifacts/architecture.md` §F3 (line 436), §I6 (line 509), §A8 (line 354) — current decisions Story 6.4 will amend; not amended here]
- [Source: `compose/app.yml:28–89` — current BFF service block; modified per Task 4]
- [Source: `compose/app.yml:91–147` — current RS service block; unchanged]
- [Source: `compose/app.yml:149–219` — current playwright service block; unchanged]
- [Source: `compose/infra.yml:10–59` — current Keycloak service block; modified per Task 5]
- [Source: `keycloak/realm-bmad-books.json:71` — proof that `${VAR}` substitution works (`"secret": "${BFF_CLIENT_SECRET}"`)]
- [Source: `keycloak/realm-bmad-books.json:80, 84, 87` — the three URL fields modified per Task 6]
- [Source: `keycloak/Dockerfile:27` — `CMD ["start-dev", "--import-realm"]` (boot-time realm import)]
- [Source: `services/bff/Dockerfile:1–13` — Stage 0 Node builder pattern (mirror for SPA Dockerfile comment style)]
- [Source: `services/bff/Dockerfile:45–46, 65` — non-root `app` user pattern]
- [Source: `services/bff/Dockerfile:72–75` — single-line `HEALTHCHECK` pattern (stdlib-only Python; SPA mirrors with Node `fetch`)]
- [Source: `services/bff/src/bff/api/auth.py:149, 232` — `redirect_uri=f"{cfg.bff_base_url}/auth/callback"` (the line that consumes `BFF_BASE_URL` for OAuth redirect_uri construction)]
- [Source: `services/bff/src/bff/auth/csrf.py:102` — `expected = self._parse_origin(settings.bff_base_url)` (CSRF Origin check anchored on BFF_BASE_URL)]
- [Source: `spa/src/server.ts:18` — `bffInternalUrl = process.env['BFF_INTERNAL_URL'] ?? 'http://localhost:8000'`]
- [Source: `spa/src/server.ts:42–49` — `app.use(createProxyMiddleware({ pathFilter: [...], target: bffInternalUrl, changeOrigin: true, xfwd: true }))`]
- [Source: `spa/src/server.ts:73–83` — `app.listen(port, ...)` with `port = process.env['PORT'] || 4000`]
- [Source: `spa/src/app/app.config.server.ts:9, 13` — `BFF_INTERNAL_URL` + `SPA_PUBLIC_ORIGIN` env consumption]
- [Source: `.env.example` — current shape; modified per Task 7]
- [Source: `docker-compose.yml:1–17` — current header comment; refreshed per Task 8]
- [External: Keycloak 26 docs — realm import + Quarkus MicroProfile Config substitution syntax `${VAR:default}`]
- [External: Compose Spec — `${VAR:-default}` shell-style substitution, `--wait` / `--wait-timeout` semantics]
- [External: Docker `node:22-slim` — Node 22 LTS, Debian-slim base, global `fetch` available]
- [External: Angular `@angular/build:application` + `outputMode: "server"` — bundles SSR deps into the server entry]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.7 (1M context) via `bmad-dev-story`, executed 2026-05-19 against baseline `ed34ac7` with Story 6.1's uncommitted working-tree diff present (per story prerequisites).

### Debug Log References

One mid-run discovery resolved without scope creep: the first `docker compose up -d --wait` after editing `keycloak/realm-bmad-books.json` showed Keycloak rejecting `redirect_uri=http://localhost:4000/auth/callback` with `LOGIN_ERROR / invalid_redirect_uri`. Root cause: the Keycloak image (`keycloak/Dockerfile:25`) **bakes** the realm JSON at image-build time via `COPY realm-bmad-books.json /opt/keycloak/data/import/realm-bmad-books.json`, so edits to the host file don't take effect until the image is rebuilt. Resolution: `docker compose build keycloak` then `up -d --wait` — admin API now shows `redirectUris=['http://localhost:4000/auth/callback']` (substitution from `${SPA_HOST_PORT:4000}` confirmed working). No code change required. **Follow-up surfaced for Story 6.4 docs sweep below.**

### Completion Notes List

**AC1 — `spa/Dockerfile` image inspection (canonical :4000 stack):**
```
ExposedPorts={"4000/tcp":{}}
User=app                                                # non-root
Entrypoint=["node","dist/spa/server/server.mjs"]
Healthcheck.Test=["CMD-SHELL","node -e \"fetch('http://localhost:4000/_health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))\""]
Image size: 350 MB                                      # node:22-slim base + 2.5 MB app payload
Runtime stage contents:
  /app/dist                                             # ONLY dist/spa/ — no node_modules
  /app/dist/spa: 2.5M
  /app/dist/spa/server: 2.0M
  fetch typeof: function                                # Node 22 global fetch confirmed
```

**AC2 — `docker compose down -v && docker compose up -d --wait`:**
All four services reached `running (healthy)` within the 120s window:
```
SERVICE           STATUS                    PORTS
bff               Up (healthy)              8000/tcp                              # NO host port
keycloak          Up (healthy)              0.0.0.0:8080->8080/tcp, :9000->9000
resource-server   Up (healthy)              8000/tcp
spa               Up (healthy)              0.0.0.0:4000->4000/tcp
```

**AC3 — `curl -L http://localhost:4000/` (anonymous → /login?return_to=%2Fbooks):**
final HTTP 200; markers present: `<app-root` ×1, `ng-server-context="ssr"` ×1, `ngh=` ×1, `<script id="ng-state"` ×1.

**AC4 — `curl http://localhost:4000/api/me` (anonymous):**
HTTP 401 with body byte-for-byte: `{"errorCode":"session_expired","message":"Session expired or not present","detail":null}`.

**AC5 — `curl http://localhost:8000/` from host:**
Exit status 7, stderr `Couldn't connect to server` (libcurl form of Connection refused). BFF still reachable from the compose network: `docker compose exec spa node -e "fetch('http://bff:8000/health')..."` returns `{"status":"ok"}`.

**AC6 — OAuth happy path completed via scripted curl (not browser):**
- Step 1 `GET /auth/login` → `302` to Keycloak with **decoded `redirect_uri=http://localhost:4000/auth/callback`**. `bff_auth_state` cookie set (`HttpOnly; Max-Age=300; Path=/; SameSite=lax`).
- Step 2 Keycloak login form rendered (no `Invalid parameter: redirect_uri` after image rebuild).
- Step 3 `POST username=testuser&password=testpassword` to Keycloak's `login-actions/authenticate?...` → `302` to `http://localhost:4000/auth/callback?state=...&code=...` ✓.
- Step 4 `GET /auth/callback` through SPA edge → BFF exchanges code → `302 Location: /` with three `Set-Cookie` headers:
  ```
  bff_auth_state=""; HttpOnly; Max-Age=0; Path=/; SameSite=lax       # cleared
  bff_session=...;  HttpOnly; Path=/; SameSite=lax
  csrf_token=...;             Path=/; SameSite=lax
  ```
- Step 5 `GET /api/me` with cookies → HTTP 200 `{"sub":"e1507290-0ad2-45fc-a33c-75327e3d301f","preferred_username":"testuser"}` ✓.
- Step 6 `GET /` with cookies → final SSR HTML at `http://localhost:4000/books` with `ngh=` + `ng-server-context="ssr"` markers ✓.
- Logout: `POST /auth/logout` with `Origin: http://localhost:4000` + `X-CSRF-Token: <token>` → HTTP 204; Set-Cookie clears both `bff_session` and `csrf_token` (`Max-Age=0`); subsequent `GET /api/me` → HTTP 401 anon envelope ✓.

  **CSRF Origin-check note (AC6 failure-prevention #2 confirmed):** Initial logout attempt without an `Origin` header returned 403 — the BFF's `CsrfMiddleware` (`services/bff/src/bff/auth/csrf.py:102`) compares the request's `Origin` against `settings.bff_base_url=http://localhost:4000`; a curl POST without `Origin` fails the check. Browser-side state-changing POSTs always include `Origin`, so this is curl-test ergonomics, not a behavior regression. The chain through `http-proxy-middleware` (`spa/src/server.ts:42–49`) preserves `Origin: http://localhost:4000` unchanged to the BFF.

**AC7 — `SPA_HOST_PORT=4100 docker compose down -v && up -d --wait`:**
- `docker compose ps spa` → `0.0.0.0:4100->4000/tcp`.
- `curl http://localhost:4100/_health` → 200 `{"ok":true}`.
- `curl -L http://localhost:4100/` → 200 at `/login?return_to=%2Fbooks` with `ngh=` + `ng-server-context="ssr"` markers.
- `curl http://localhost:4100/api/me` → 401 anon envelope.
- `GET /auth/login` decoded `redirect_uri` → **`http://localhost:4100/auth/callback`**.
- Keycloak admin API confirms imported realm has `redirectUris=['http://localhost:4100/auth/callback']`, `webOrigins=['http://localhost:4100']`, `post.logout.redirect.uris='http://localhost:4100/*'` — all five substitution sites flowed end-to-end.
- Restored to canonical `:4000` via `docker compose down -v && docker compose up -d --wait` (Task 9.8).

**AC8 — healthcheck shape:** SPA compose-level healthcheck uses Node `fetch` against `/_health` (single-line CMD list form, mirroring BFF stdlib pattern); BFF healthcheck (`compose/app.yml`) unchanged.

**AC9 — scope-leak audit:**

Files this story touched (the AC9 allowlist deliverables, all present in `git status --short`):
- `spa/Dockerfile` — NEW (~60 lines, 3-stage Node build, non-root `app`, Node `fetch` healthcheck)
- `spa/.dockerignore` — NEW (~28 lines)
- `compose/app.yml` — header refresh + BFF `BFF_BASE_URL` flip + `ports` block dropped + new `spa:` service block
- `compose/infra.yml` — `SPA_HOST_PORT` env pass-through on `keycloak`
- `keycloak/realm-bmad-books.json` — three `${SPA_HOST_PORT:4000}` substitutions (lines 80, 84, 87)
- `.env.example` — appended optional `SPA_HOST_PORT` block
- `docker-compose.yml` — header comment refresh
- `_bmad-output/implementation-artifacts/6-2-spa-dockerfile-compose-service-keycloak-realm-port.md` (THIS file) — status flips, Dev Agent Record, File List, Change Log, Tasks/Subtasks checkboxes
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `6-2`: ready-for-dev → in-progress → review

All OTHER working-tree changes shown by `git status --short` at story close (`spa/angular.json`, `spa/package.json`, `spa/package-lock.json`, `spa/tsconfig.app.json`, `spa/proxy.conf.json` deletion, `spa/src/app/app.config.ts`, both interceptor `.ts` + `.spec.ts` pairs, all `spa/src/app/shared/http/ssr-*.ts`, `spa/src/main.server.ts`, `spa/src/server.ts`, `_bmad-output/implementation-artifacts/6-1-...md`, `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-19.md`) were **pre-existing in the working tree** at story-start (per the session-start git snapshot) and explicitly belong to Story 6.1's review surface — the story prerequisites name them.

**Anomalies:**

- `_bmad-output/implementation-artifacts/6-3-bff-cleanup-supersede-story-1-14.md` was NOT in the session-start git snapshot but appeared as untracked mid-session (filesystem mtime `2026-05-19 14:07`). This dev session did not author or edit it — it appeared from outside the workflow (likely a parallel context-prep run for Story 6.3). Surfaced per AC9 anomalies guidance; **not patched in 6.2**.
- `_bmad-output/implementation-artifacts/deferred-work.md` showed ` M` in both the session-start snapshot and at story close; not touched by this story.

**Intentional regressions / temporary state at 6.2 close (documented, all in scope of later Epic-6 stories):**

- SPA HTML responses carry NO CSP header until Story 6.4 moves CSP source BFF → SPA per architecture A8 amendment. The BFF's `SecurityHeadersMiddleware` still attaches CSP to JSON responses, but JSON CSP is not browser-evaluable.
- `just e2e-up` is indeterminate until Story 6.4 sweeps `compose/app.e2e.yml` + `e2e/playwright.config.ts` `--host-resolver-rules` (still pinned to `:8000`). Not exercised in this story.
- Host-side `cd spa && npm start` already broken by Story 6.1's `proxy.conf.json` deletion; containerized SPA edge is the documented dev path.
- Story 1.14's SPA-in-BFF static-serve code path (BFF Dockerfile Stage 0 + `_register_spa` + `test_static.py`) stays LIVE in the BFF image — unreachable from the browser post-6.2 (no BFF host port) but physically present. Story 6.3 removes it.

**Failure-prevention follow-up surfaced for Story 6.4 docs sweep:**

The realm-JSON edit gotcha has TWO parts, not one: (1) Keycloak only re-imports on an empty data volume — `down -v` (already in AC2 wording and `.env.example`); AND (2) the Keycloak image **bakes** the realm JSON at image-build time (`keycloak/Dockerfile:25 COPY realm-bmad-books.json ...`), so a host-side edit doesn't take effect until `docker compose build keycloak` runs. The smoke-run docs (`docs/smoke-run.md` Run Records owned by 5.4 / 6.4) should add this as a setup-step note. No story-6.2 doc change made (out of scope per AC9 blocklist).

### File List

**NEW (2):**
- `spa/Dockerfile`
- `spa/.dockerignore`

**MODIFIED (5):**
- `compose/app.yml`
- `compose/infra.yml`
- `keycloak/realm-bmad-books.json`
- `.env.example`
- `docker-compose.yml`

**Artefacts updated (2):**
- `_bmad-output/implementation-artifacts/6-2-spa-dockerfile-compose-service-keycloak-realm-port.md` (THIS file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-19 | 1.0 | Initial story implementation: SPA Dockerfile + .dockerignore (per-service `../spa` context); compose `spa:` service block on `${SPA_HOST_PORT:-4000}`; BFF host-port removed + `BFF_BASE_URL` flipped to `http://localhost:${SPA_HOST_PORT:-4000}`; Keycloak realm `${SPA_HOST_PORT:4000}` substitution at three URL sites + env pass-through; `.env.example` `SPA_HOST_PORT` documented; `docker-compose.yml` header refresh. All ACs 1–8 verified live against `docker compose up`; OAuth happy path completed end-to-end via curl at both `:4000` and `:4100`. | Claude Opus 4.7 (1M context) |
| 2026-05-19 | 1.1 | Code review pass: 3-layer adversarial review (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Acceptance Auditor: 15 PASS / 0 PARTIAL / 0 FAIL / 0 NEW. 4 patches applied (P1 healthcheck `.catch` logs error before exit on both Dockerfile + compose-level probes; P2 `init: true` on spa service to fix Node-as-PID-1 SIGTERM handling; P3 `.env*` added to `spa/.dockerignore`; P4 `**/*.spec.ts` added to `spa/.dockerignore`). 5 defers logged D154–D158 in `deferred-work.md` (all cross-cutting / pre-existing convention items). ~50 findings dismissed as noise (~80% targeted `spa/src/server.ts` — Story 6.1 territory, already handled by 6.1's review pass). Live post-patch verification: image rebuilt clean, spa container recreated, `docker inspect spa --format '{{.HostConfig.Init}}'` returns `true`, AC3/AC4/AC8 probes re-pass. Story status: review → done. | Claude Opus 4.7 (1M context) |
