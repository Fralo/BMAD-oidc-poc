# Smoke Run — baseline stack (SPA-in-BFF production build)

**Profile:** none — baseline stack is unconditional (Keycloak + BFF [SPA baked in] + Resource Server). The D140/D141 follow-up (baseline `5f9b0f7`) retired the `default` / `dev` profile names.
**Build form:** `docker compose up --build` (no `--profile` flag, no `-f` overlay).
**Browser:** any modern desktop browser (Chrome, Firefox, Safari, Edge). No mobile / responsive testing — PRD §4 explicitly excludes responsive layout.
**Reference:** PRD §10 J1–J6 (`_bmad-output/planning-artifacts/PRD.md` lines 95–102); epic AC at `_bmad-output/planning-artifacts/epics.md` lines 1892–1933.

## Prerequisites

Before starting, confirm:

- Docker + Docker Compose v2.20+ installed (verify: `docker compose version`).
- The repo is cloned locally; `cd` is the repo root.
- `tools/fastapi-archetype/` exists (the BFF and RS reference the archetype's directory structure; gitignored).
- `.env` exists at the repo root (copied from `.env.example`); `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`, `BFF_CLIENT_SECRET`, `TEST_RESET_TOKEN` are set. The last is unused by the baseline stack but must still be present because Compose may parse the overlay file for variable interpolation on some invocations.
- No prior stack is running on ports 8000 / 8080 / 9000 (verify: `lsof -iTCP:8000,8080,9000 -sTCP:LISTEN` returns empty).

## Known setup workarounds (apply before step 4)

D140 and D141 (originally surfaced by Story 5.4's Mode-B smoke) were closed by the D140/D141 follow-up at baseline `5f9b0f7`. Only D142 remains live for this smoke procedure.

1. **D140 — CLOSED.** Bare `docker compose up` now activates the baseline stack (Keycloak + BFF + RS). The retired `default` / `dev` profile names were dropped; only the `e2e` profile remains, scoping the Playwright runner.
2. **D141 — CLOSED.** The root `.env` is now the single canonical entry point. Per-service `services/<svc>/.env` files were retired; topology constants moved into per-service `environment:` blocks in `compose/app.yml`.
3. **D142 — LIVE.** Baseline stack leaves `AUTH_TYPE=none` on the Resource Server (no `AUTH_TYPE` in the RS `environment:` block in `compose/app.yml`, defaulting to the archetype's `none`); only the `compose/app.e2e.yml` overlay activates `oidc_bearer`. Under the baseline stack, RS scope enforcement is bypassed (synthetic admin) — J3 / J4 / J6 journeys functionally pass but the prod-shaped auth surface is auth-degraded. Workaround until D142 is closed:
   ```bash
   # In compose/app.yml, in the resource-server `environment:` block, add:
   #   AUTH_TYPE: oidc_bearer
   # Then re-up the stack.
   ```

## Checklist

The 13 steps below are the operator-driven walk-through. Each is a single `[ ]`
checkbox the developer flips to `[x]` after completing it against a real
desktop browser at `http://localhost:8000`. **Apply the D142 workaround above
before step 4 to exercise real scope enforcement (otherwise the stack runs
auth-degraded — still functionally green but the security review's
attestations are not actually exercised).**

1. [x] Fresh clone of the repo (or `git clean -xdf` from the repo root to mimic a clean tree — careful: this wipes ignored files). *(Mode-B dev-pass: verified at baseline `fb751ec`.)*
2. [x] Setup per README: archetype clone (`tools/fastapi-archetype/`), `.env` from `.env.example` with the four required keys populated. *(Mode-B dev-pass at `fb751ec`: per-service `.env` files also copied per the then-live D141 workaround — no longer needed at `5f9b0f7+`.)*
3. [x] `docker compose down -v` to clear any prior `bff_data` / `rs_data` named volumes (idempotent — exits 0 even when nothing was running). *(Mode-B dev-pass: idempotent return — no prior project state.)*
4. [x] `docker compose up --build` (baseline stack — no `--profile` flag, no `-f` overlay). Run in foreground OR `-d` for detached. *(Mode-B dev-pass at `fb751ec`: used `docker compose --profile default up --build -d`, the then-live D140 workaround.)*
5. [x] Wait for all healthchecks. Verify via `docker compose ps`: `keycloak`, `bff`, `resource-server` all show `(healthy)`. Start period 30s; observed warm-cache healthy-time on this host was 32–42 s post-start (well inside the 90–120 s "typical" envelope previously documented). *(Mode-B dev-pass: poll loop until all three healthy; transcript below.)*
6. [ ] Open `http://localhost:8000` in a desktop browser. The SPA bootstraps; an unauthenticated user lands on `/login` (the auth guard bounces from `/books`).
7. [ ] **J1 — First-time login.** Click "Log in" → browser is redirected to `http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth?...` (Keycloak login form). Enter `testuser` / `testpassword` → Keycloak submits → returns to `http://localhost:8000/books` with the identity visible in the top chrome (username or initial visible).
8. [ ] **J2 — Manage books.** Add a book (`Dune`, `688` pages, status `to-read`) → row appears at the top of the list. Change status to `reading` via the inline select → change is visible immediately (optimistic UI). Edit the title to `Dune Messiah` → row updates after PUT round-trip. Click "Delete" → native browser confirm dialog → confirm → row removed.
9. [ ] **J4 — Adjust reading speed.** Navigate to `/settings` via the top-chrome "Settings" link. Set pages-per-hour to `30` → click "Save" → button briefly relabels to "Saved" (~1 s pulse). Reload the page (`Cmd-R` / `Ctrl-R`) → value still shows `30` (persisted to the Resource Server).
10. [ ] **J3 happy path.** Navigate back to `/books`. Add a 600-page book (any title; status `to-read`). Click "Estimate" → during the round-trip, the button briefly shows "Estimating…" (may be too fast to observe on a warm round-trip — that is acceptable). Formatted duration appears next to a "Re-estimate" button: `≈ 20 h` (math: 600 pages ÷ 30 pages/hour = 1200 minutes = 20 h exact; `format_duration` emits the U+2248 ALMOST EQUAL TO glyph + `20 h`; see `services/resource-server/src/resource_server/services/duration.py` `_PREFIX` + `estimate_service.py:63` ceiling-div formula). Navigate back to `/settings`, change speed to `60`, click "Save", return to `/books`. Click "Re-estimate" on the 600-page book → new result is `≈ 10 h` (600 ÷ 60 = 600 min = 10 h exact). Re-estimate result is strictly smaller than the speed-30 result, confirming the speed change took effect.
11. [ ] **J3 precondition (fresh-user 412 path).** Click "Log out" in the top chrome → bounce to `/login`. Click "Log in" → Keycloak login form → enter `freshuser` / `freshpassword` (the seeded user with NO reading-speed row). Returned to `/books`. Add a book (any title and page count; status `to-read`). Click "Estimate" → instead of a duration, see the precondition copy: `Set your reading speed in Settings to enable estimates` (the word `Settings` is a clickable in-app link — `routerLink="/settings"`). Click the `Settings` link → navigates to `/settings` (no full reload, SPA route change). See `spa/src/app/books/estimate-cell.html` lines 18–29, copy export `ESTIMATE_CELL_PRECONDITION_PREFIX` at `estimate-cell.ts:30`.
12. [ ] **J5 — Logout and re-protection.** Click "Log out" in the top chrome → top-chrome identity area empties (logged-out state visible) → URL ends with `/login`. Attempt to navigate manually to `http://localhost:8000/books` → bounces back to `http://localhost:8000/login?return_to=%2Fbooks` (the auth guard re-protects the route and preserves the return target via URL-encoded query param).
13. [ ] **J6 — Resource server unavailable.** Log in again as `testuser` / `testpassword` (Keycloak may have an active SSO session and skip the password prompt; that is acceptable). On `/books`, in another terminal run `docker compose stop resource-server` → the RS container goes down (`docker compose ps` shows `resource-server` as `Exited`). Back in the browser on `/books`, click "Estimate" on any book (a fresh row if needed) → the row shows the error copy `Service unavailable — try again shortly` (rendered in the error color — typically a red-ish foreground per the SPA's error-message component; the byte string is exported as `ESTIMATE_CELL_J6_COPY` at `estimate-cell.ts:27`). Run `docker compose start resource-server` → wait for the RS healthcheck to flip back to `(healthy)` (`docker compose ps`). Back in the browser, click "Estimate" again on the same row → a real formatted duration appears (the prior error state clears).

## Run Record

> **Historical record — frozen at commit `fb751ec`.** This Run Record captures the Mode-B smoke at the moment it was performed. D140 and D141 cited below as anomalies have since been closed by the D140/D141 follow-up at baseline `5f9b0f7`; D142 remains live. The transcript and command forms below reflect the then-current per-service-`.env` + `--profile default` model, not today's baseline-stack model.

- **Run date:** 2026-05-18
- **Commit SHA:** `fb751ec` (full SHA `fb751ec7f67b866450754997e449f79efbd763cb`; merge commit for Story 5.2; `git rev-parse HEAD` at smoke time).
- **Operator:** claude-opus-4-7 (dev agent — Mode B partial-smoke close).
- **Host environment:** macOS (darwin 25.4.0) / Docker 29.4.3 / Docker Compose v5.1.3.
- **Mode chosen:** **Mode B** (programmatic agent with operator follow-up for browser-required steps). Reason: dev agent has no desktop-browser capability; cannot click through the OAuth round-trip or interact with SPA controls.
- **Anomalies:**
  - **PENDING — operator browser walk-through required:** steps 6-13 (8 steps total — step 6 "open browser at http://localhost:8000" + J1 step 7 + J2 step 8 + J4 step 9 + J3 happy step 10 + J3 precondition step 11 + J5 step 12 + J6 step 13). The dev agent verified the SPA bundle is served end-to-end (step 6 surrogate probe), the OAuth redirect is wired (J1 surrogate — full PKCE params visible in the 302 Location), unauthenticated `/api/me` returns 401 with the project error envelope, and the RS killswitch path used by step 13 works (`docker compose stop resource-server` + healthcheck-recovery on `docker compose start resource-server` in ~6 s). The eight pending steps require an operator with a real desktop browser at `http://localhost:8000`.
  - **D140 — Bare `docker compose up` does not start the default profile.** All three services in `compose/infra.yml` + `compose/app.yml` declare `profiles: [default, dev, e2e]`; Compose v2/v5 with `include:` excludes profiled services unless `--profile <name>` is set. The architecture (`_bmad-output/planning-artifacts/architecture.md:1294`), the README (this file's neighbor, lines 4 + 30), and the epic AC for Story 5.4 step 4 all say `docker compose up` (no flag). Actual behavior on this host: bare `docker compose up` exits with `no service selected`. The canonical form is `docker compose --profile default up --build` (or `COMPOSE_PROFILES=default docker compose up --build`). The smoke checklist above pins the explicit form. See deferred-work.md → D140.
  - **D141 — Per-service `.env` files are required, not just the repo-root `.env`.** `compose/app.yml` declares `env_file: ../services/bff/.env` and `../services/resource-server/.env` on the BFF and RS services. Bringing up the default profile with only the repo-root `.env` (the model `.env.example`'s header describes) errors out with `env file ../services/bff/.env not found`. Operator must additionally `cp services/bff/.env.example services/bff/.env` and `cp services/resource-server/.env.example services/resource-server/.env`. See deferred-work.md → D141.
  - **D142 — Default profile leaves `AUTH_TYPE=none` on the Resource Server.** `services/resource-server/.env.example:57` has `#AUTH_TYPE=oidc_bearer` commented out; only `compose/app.e2e.yml` flips it on. Under the default profile, RS runs in `AUTH_TYPE=none` (archetype synthetic-admin mode — JWT signature / scope / issuer / audience NOT validated). J3 / J4 / J6 journeys would functionally pass but the **scope-enforcement surface that PRD §8 + Story 5.2 §5 attest to is not exercised** — the prod-shaped smoke is auth-degraded vs. e2e profile. See deferred-work.md → D142.
  - **D143 — `/api/me` 401 envelope `message` wording.** Actual: `Session expired or not present`. Acceptable as a 401 surface; minor wording drift from Story 5.2's documented envelope semantics. Not a defect; logged for documentation consistency only. See deferred-work.md → D143.
- **Optional screenshots:** none captured (Mode B has no browser surface to screenshot).
- **Verdict:** **PASS WITH ANOMALIES** — Mode-B partial-smoke close. Steps 1–5 + the 3 HTTP probes + the RS killswitch surrogate are all green at baseline `fb751ec`. Steps 6–13 require operator follow-up via real desktop browser before the story moves to `done`. Four new defers (D140-D143) logged; D140 + D141 + D142 will block a clean Mode-A walk-through unless the operator applies the workarounds above (which mirror what the smoke checklist now spells out explicitly).

### Mode-B HTTP-probe transcript (steps 1–5 + 3 probes + J6 surrogate)

```text
$ git rev-parse HEAD
fb751ec7f67b866450754997e449f79efbd763cb

$ docker compose down -v
Warning: No resource found to remove for project "e5s4".

$ # Setup step (D141 workaround): copy per-service .env files in addition to the root .env.
$ cp .env.example .env
$ cp services/bff/.env.example services/bff/.env
$ cp services/resource-server/.env.example services/resource-server/.env

$ # Setup step (D142 workaround): enable oidc_bearer on the RS for the default profile.
$ sed -i.bak 's/^#AUTH_TYPE=oidc_bearer/AUTH_TYPE=oidc_bearer/' services/resource-server/.env

$ docker compose --profile default up --build -d
[+] Building ... (35/35) FINISHED
 ✔ Image e5s4-resource-server  Built
 ✔ Image e5s4-keycloak         Built
 ✔ Image e5s4-bff              Built
 ✔ Network e5s4_default        Created
 ✔ Volume e5s4_bff_data        Created
 ✔ Volume e5s4_rs_data         Created
 ✔ Container keycloak          Started → Healthy
 ✔ Container bff               Started
 ✔ Container resource-server   Started

$ # Poll until all healthy
$ until [ "$(docker compose --profile default ps --format '{{.Health}}' | sort -u | tr -d ' ')" = "healthy" ]; do sleep 3; done
$ docker compose --profile default ps --format "table {{.Name}}\t{{.State}}\t{{.Status}}"
NAME              STATE     STATUS
bff               running   Up 32 seconds (healthy)
keycloak          running   Up 42 seconds (healthy)
resource-server   running   Up 32 seconds (healthy)

$ # Probe 1 — BFF serves the SPA bundle at GET /
$ curl -fsS -o /tmp/spa.html -w "HTTP %{http_code}\n" http://localhost:8000/
HTTP 200
$ grep -c '<app-root>' /tmp/spa.html
1

$ # Probe 2 — /auth/login returns 302 → Keycloak authorize endpoint with full PKCE params
$ curl -sS -o /dev/null -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:8000/auth/login
HTTP 302 → http://localhost:8080/realms/bmad-books/protocol/openid-connect/auth?client_id=bmad-books-bff&response_type=code&scope=openid+reading-speed%3Aread+reading-speed%3Awrite&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Fcallback&state=<random>&nonce=<random>&code_challenge=<S256>&code_challenge_method=S256

$ # Probe 3 — /api/me returns 401 + project error envelope when unauthenticated
$ curl -sS -w "\nHTTP %{http_code}\n" http://localhost:8000/api/me
{"errorCode":"session_expired","message":"Session expired or not present","detail":null}
HTTP 401

$ # J6 surrogate — RS killswitch + healthcheck recovery
$ docker compose --profile default stop resource-server
 Container resource-server Stopped
$ docker compose --profile default ps -a resource-server --format "{{.Name}}\t{{.State}}\t{{.Status}}"
resource-server  exited  Exited (0) Less than a second ago

$ docker compose --profile default start resource-server
 Container resource-server Started
$ # Wait for healthcheck recovery
$ until [ "$(docker compose --profile default ps resource-server --format '{{.Health}}')" = "healthy" ]; do sleep 2; done
$ docker compose --profile default ps resource-server --format "{{.Name}}\t{{.State}}\t{{.Status}}"
resource-server  running  Up 6 seconds (healthy)

$ # Final tear-down (no -v: volumes preserved for the operator's follow-up Mode-A run)
$ docker compose --profile default down
 Container bff               Removed
 Container resource-server   Removed
 Container keycloak          Removed
 Network e5s4_default        Removed
```

### Operator follow-up checklist

When an operator completes the browser walk-through:

1. Bring the stack back up with bare `docker compose up --build` (post-D140/D141 follow-up at baseline `5f9b0f7`+; the historical `--profile default --build` form above was the `fb751ec` workaround, now retired). Volumes were preserved at tear-down so a re-`down -v` is recommended for a true fresh-state walk-through.
2. Walk through each `[ ]` step 6–13 in a desktop browser at `http://localhost:8000`.
3. For each completed step, flip `[ ]` → `[x]` in the Checklist section above.
4. If a step deviates from the documented behavior, add a per-step entry under Anomalies with the observed deviation and any defer ID logged.
5. After all 8 pending steps are `[x]`, change the Verdict from `PASS WITH ANOMALIES` to `PASS` (or leave it as `PASS WITH ANOMALIES` if any new anomaly was recorded). Commit the filled-out file.

The dev agent's Mode-B close is sufficient for the story to move to `review`; the operator's follow-up walk-through is the bridge from `review` to `done`.
