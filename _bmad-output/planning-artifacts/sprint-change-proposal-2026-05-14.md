---
title: Sprint Change Proposal — Remove Observability Stack
date: 2026-05-14
project: BMAD_books
approved_by: Nearformer (via /bmad-correct-course args, 2026-05-14)
scope_classification: Major (planning-artifact rewrite across PRD, epics, architecture, sprint status, memory)
---

# Sprint Change Proposal: Remove Observability Stack

## 1. Issue Summary

The educational value of the project — demonstrating OAuth2/OIDC + BFF + JWKS + scope enforcement in a docker-compose-runnable form — does not require, and is not improved by, shipping a full observability sidecar stack (OTEL Collector, Jaeger, Prometheus, Grafana). The stack adds four containers, additional env vars, a `compose/observability.yml` include, two `observability/` source folders per backend service, two extra checks in the J-smoke run, and one whole Additional Requirement (AR29) — none of which exercise the architectural concepts the project exists to teach.

**Trigger:** Maintainer scope review on 2026-05-14, ahead of any implementation work being started. All five epics and all 30+ stories are still in `backlog` status per `sprint-status.yaml`; no rollback or code revert is required.

**Evidence:**
- `epics.md` lines 92–93: AR29 mandates the four-container observability stack as a sidecar requirement, while no other requirement (PRD §10 journeys, NFR1–13, AR1–AR34 sans 29) depends on traces or metrics being captured.
- `epics.md` Story 5.4 lines 1933–1934: smoke checklist steps #14 (Jaeger trace lookup) and #15 (Grafana metrics check) are the only manual verifications of the observability stack — the rest of the journeys verify themselves through SPA behavior and HTTP responses.
- Architecture lines 119, 1346: observability components explicitly noted as having no app-side dependents — they are pure sidecars.

## 2. Impact Analysis

### Epic Impact

| Epic | Impact |
|---|---|
| Epic 1 | Moderate — Story 1.1 loses ~25% of its ACs (the observability sidecar sub-stack), Story 1.3 loses 1 AC block (OTEL trace + Prometheus scrape verification). |
| Epic 2 | None — no observability touchpoints in epic 2 stories. |
| Epic 3 | Light — Story 3.1 loses 1 AC block (same as 1.3); Story 3.5 has 1 AC sentence amended (OTEL httpx instrumentor reference dropped); Epic 3 user outcome description loses an "observable via OTEL traces" clause. |
| Epic 4 | None directly. |
| Epic 5 | Light — Story 5.3 README structure loses 3 port-table entries + "observability" mentions in dev/architecture sections; Story 5.4 loses 2 smoke checklist steps. Epic 5 user outcome description loses Jaeger/Grafana references. |

### Artifact Impact

| Artifact | Touchpoints | Change Type |
|---|---|---|
| `PRD.md` | 0 existing observability mentions; 1 addition to §12 Out of Scope | Additive |
| `epics.md` | 26 lines across NFR10, AR15, AR26, AR29, AR30, Epic 1/3/5 descriptions, Story 1.1, Story 1.3, Story 3.1, Story 3.5, Story 5.3, Story 5.4 | Delete + amend; AR30 renumbers to AR29 |
| `architecture.md` | 26 lines across §"Scale & Complexity", §"Technical Constraints", §"Cross-Cutting Concerns", §"API Communication", §"Compose Composition", §"Env Vars", §"Naming Patterns", §"Project Structure" (×2), §"Communication Patterns", §"Logging Conventions", §"File Organization Patterns", §"Operational Details", §"Coherence Validation", §"Decision Impact" | Delete + amend |
| `ux-design-specification.md` | 1 mention (line 173) | None — statement is philosophical, not a feature requirement; remains accurate after removal |
| `implementation-readiness-report-2026-05-14.md` | 1 reference (line 356) | Amend the Story 1.1 title in the "Recommended Next Steps" section |
| `sprint-status.yaml` | 1 story id key | Rename `1-1-repo-scaffold-compose-skeleton-observability-sidecars` → `1-1-repo-scaffold-compose-skeleton` |
| `~/.claude/.../memory/project_bmad_books_backend_archetype.md` | 2 lines (description + observability bullet) | Amend — archetype mandate retained, but observability carved out as a project-specific de-mandate |

### Technical Impact

- **Compose file count drops by 1.** `compose/observability.yml` is no longer specified.
- **Env vars drop by 2.** `OTEL_EXPORT_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` are removed from `.env.example`.
- **Source folder structure simplifies.** `src/<svc>/observability/{tracing,metrics}.py` and the mirroring `tests/observability/` are removed from both BFF and RS layouts.
- **`/metrics` HTTP route is removed** from both backend services (it was the Prometheus scrape endpoint). `/health`, `/docs`, `/redoc` remain.
- **Archetype OTEL wiring obligation is dropped.** The archetype repo (`github.com/tommaso-meledina/fastapi-archetype`) remains mandatory for Python 3.14 + FastAPI + SQLModel + uv + Ruff + ty + pytest + error envelope + auth scaffolding + AOP logging. Its OTEL/Prometheus boilerplate, if present in the scaffolded output, may be left inert or removed — there is no obligation to wire it to an exporter.
- **X-Request-Id header decision.** Previously stated as "set by OTEL middleware" (architecture line 562). The header is retained for log correlation and will be generated by a simple UUID middleware on each request — a one-file replacement, no library dependency beyond stdlib.

### What is NOT impacted

- All six PRD journeys (J1–J6) and their E2E specs.
- All thirteen NFRs except NFR10 (which loses one parenthetical "observability stack" mention from its component list).
- All ARs except AR29 (deleted) and AR15/AR26/AR30 (amended); AR30 renumbers to AR29.
- The SPA, Keycloak, BFF↔RS bearer flow, JWKS validation, scope enforcement, CSRF middleware, refresh-and-replay logic, error envelope contract, and all UX behavior.

## 3. Recommended Approach

**Selected path: Option 1 — Direct Adjustment.**

- **Effort:** Low. ~20 line-level edits across three artifacts plus one sprint-status rename and one memory amendment.
- **Risk:** Low. No story is in progress; no implementation code exists; no AC under review depends on observability behavior except the ones being explicitly removed.
- **Timeline impact:** Net negative effort — Story 1.1 shrinks by ~25%, Story 5.4 shrinks by 2 checklist steps, Stories 1.3 / 3.1 each shrink by 1 AC block. Sprint planning velocity should improve slightly.

Rationale: This is the most ambitious of the three options the maintainer evaluated (the others being "make it optional" or "keep only OTEL no UI"). It is also the one that produces the cleanest planning artifacts — there is no half-state where the docs reference an optional sidecar that may or may not be wired up. The educational reference becomes tighter, not weaker, because the OAuth/OIDC concepts are unchanged and the docker-compose surface drops to exactly the services that participate in the demonstrated flows.

## 4. Detailed Change Proposals

### 4.1 PRD.md

**File:** `_bmad-output/planning-artifacts/PRD.md`

- **§7 Application Capabilities:** No change required. (User args mention §7, but §7 contains no observability content currently. Confirming as a no-op.)
- **§12 Out of Scope:** Add new bullet making the de-mandate explicit:

  ```
  - Observability tooling (distributed tracing collector, metrics aggregator, dashboards). The project does not deploy OTEL Collector, Jaeger, Prometheus, or Grafana. Structured logging remains in place as the only operational-visibility surface.
  ```

### 4.2 epics.md

**File:** `_bmad-output/planning-artifacts/epics.md`

**NFR10 (line 37) — amend:**

> OLD: `... Every component (SPA, BFF, RS, Keycloak, databases, observability stack) runs in Docker. ...`
>
> NEW: `... Every component (SPA, BFF, RS, Keycloak, databases) runs in Docker. ...`

**AR15 (line 72) — amend:** Remove `/metrics` from the non-versioned infra-route list. Resulting list: `/auth/login`, `/auth/callback`, `/auth/logout`, `/api/me`, `/health`, `/docs`, `/redoc`.

**AR26 (line 89) — amend:** Compose composition no longer includes `compose/observability.yml`; only `compose/infra.yml` (Keycloak) and `compose/app.yml` (BFF, RS, SPA prod). Profile description for `default` and `dev` loses the "+ observability" trailer.

**AR29 (lines 92, full bullet) — delete entirely.**

**AR30 (line 93) — renumber to AR29; amend env-var list** to remove `OTEL_EXPORT_ENABLED` and `OTEL_EXPORTER_OTLP_ENDPOINT`.

**Epic 1 scope (line 150) — delete the full "Observability sidecars wired from day one" bullet.**

**Epic 3 user outcome (line 174) — amend:** Drop the closing sentence `The cross-service call is observable end-to-end via OTEL traces.`

**Epic 5 user outcome (line 203) — amend:**

> OLD: `... They can observe traces in Jaeger and metrics in Grafana, read a documented security review ...`
>
> NEW: `... They can read a documented security review ...`

**Epic 5 note (line 214) — amend:** Remove `the observability stack wiring,` from the list of items that don't live in Epic 5.

**Epic 1 intro (line 220) — amend:** Remove `observability sidecars,` from the prose.

**Story 1.1 (lines 222–259) — retitle and rewrite.**

- Title: `### Story 1.1: Repo scaffold + compose skeleton`
- User story body: drop the `the observability sidecars defined` and `OTEL traces are visible from the first BFF deploy` clauses.
- AC block at lines 237–239: shrink to two compose-include targets (`infra.yml`, `app.yml`); delete the `compose/observability.yml` AC line.
- AC block at lines 246–249: remove `OTEL_EXPORT_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` from the `.env.example` enumeration.
- AC block at lines 252–255: delete the `docker compose --profile default up -d otel-collector jaeger prometheus grafana` verification AC and the Grafana data-source AC.

**Story 1.3 (line 300) — amend:** In the archetype-layout AC, remove `OTEL + Prometheus wiring,` from the bullet list of archetype-provided files.

**Story 1.3 ACs (lines 327–330) — delete the full Given/When/Then block** about observability sidecars + Jaeger + Prometheus scrape.

**Story 3.1 (line 1140) — amend:** Same as 1.3 — remove `OTEL + Prometheus wiring,` from the archetype-layout AC.

**Story 3.1 ACs (lines 1165–1168) — delete the full Given/When/Then block** about observability sidecars + Jaeger + Prometheus scrape on the RS.

**Story 3.5 (line 1344) — amend:**

> OLD: `... Then it wraps an httpx.AsyncClient instrumented with the archetype's OTEL httpx instrumentor (so trace context propagates SPA → BFF → RS per AR21), ...`
>
> NEW: `... Then it wraps a plain httpx.AsyncClient, ...`

**Story 5.1 (line 1789) — amend:** In the deliberate-exclusions example list, drop `OTEL bootstrap glue` and replace with another archetype-emitted boilerplate example, or shorten the parenthetical.

**Story 5.3 (line 1885) — amend:**

> OLD: `... short prose summary of the five-component topology (SPA, BFF, Resource Server, Keycloak, observability stack) ...`
>
> NEW: `... short prose summary of the four-component topology (SPA, BFF, Resource Server, Keycloak) ...`

**Story 5.3 (line 1887) — amend:** Dev workflow description loses the `+ observability` trailer; the ports table loses the Jaeger, Prometheus, and Grafana rows.

**Story 5.4 ACs (lines 1933–1934) — delete both steps** (Observability check + Metrics check). Renumber remaining steps so the smoke checklist is steps 1–13.

### 4.3 architecture.md

**File:** `_bmad-output/planning-artifacts/architecture.md`

- **Line 55** — drop `+ the archetype-provided observability stack (OTEL Collector, Jaeger, Prometheus, Grafana)` from the component count parenthetical.
- **Line 79** — delete the `Observability:` bullet from the archetype-locked decisions list.
- **Line 80** — remove `/metrics` from the infra-routes list.
- **Line 114** — amend: `single docker-compose.yml merging Keycloak, SPA, BFF, RS, and the BFF DB` (drop "the archetype's observability stack with").
- **Line 119 (Cross-Cutting Concern #12)** — delete the entire bullet about distributed tracing & metrics.
- **Line 362** — remove `/metrics` from non-versioned mechanics list.
- **Line 476** — delete the `compose/observability.yml` line from the repo-structure ASCII tree.
- **Lines 488–489** — amend profile descriptions: `default` becomes `Keycloak + BFF + RS + SPA`; `dev` becomes `Keycloak + BFF + RS` (SPA on host).
- **Line 508** — remove `OTEL_EXPORT_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT` from the env-var enumeration.
- **Line 562** — amend: `X-Request-Id (set by a simple UUID middleware in the request pipeline)`.
- **Lines 607, 609** — delete the `observability/` folder from the `src/<svc>/` tree and from the `tests/` mirror comment.
- **Line 762** — delete the `Propagates OTEL trace context ...` bullet from the BFF→RS client behavior list.
- **Line 793** — amend: `All logs structured (JSON output via the archetype's logging config).` (drop the trace_id/span_id injection clause).
- **Line 880** — delete the `compose/observability.yml` line from the complete project directory ASCII tree.
- **Lines 930–933** — delete the BFF `observability/` folder block.
- **Lines 1000–1003** — delete the RS `observability/` folder block.
- **Line 1212** — delete the `| Tracing + metrics | services/{bff,resource-server}/src/.../observability/ |` row from the Cross-Cutting Concerns Mapping table.
- **Lines 1223–1224** — delete bullets #5 (OTEL Collector) and #6 (Prometheus scrape) from the Internal communication list; renumber as needed.
- **Line 1280** — amend: `Backend: feature-by-layer (api/, services/, auth/, core/, db/, aop/) per archetype.` (drop `observability/`).
- **Line 1292** — amend: `No backend static assets (/health, /docs, /redoc are dynamic).` (drop `/metrics`).
- **Line 1306** — amend: ``docker compose --profile dev up`` brings up Keycloak + BFF + RS; SPA is excluded so `ng serve` provides HMR. (drop the OTEL/Jaeger/Prometheus/Grafana clause).
- **Line 1346** — delete the `OTEL / Jaeger / Prometheus / Grafana — these are observability sidecars; ...` bullet from the health-checks list.
- **Line 1365** — amend: `/health, /docs, /redoc` (drop `/metrics`).
- **Line 1412** — amend: drop `; observability lives in its own compose include` from the structure-alignment bullet.
- **Line 1530** — amend the "eliminates bike-shedding" example to drop `observability wiring`; substitute another archetype-decided concern (e.g., `pydantic-settings config` or `the AOP log_io decorator`).

### 4.4 sprint-status.yaml

**File:** `_bmad-output/implementation-artifacts/sprint-status.yaml`

- Rename key `1-1-repo-scaffold-compose-skeleton-observability-sidecars: backlog` → `1-1-repo-scaffold-compose-skeleton: backlog`.

### 4.5 implementation-readiness-report-2026-05-14.md

**File:** `_bmad-output/planning-artifacts/implementation-readiness-report-2026-05-14.md`

- **Line 356** — amend: `First implementation story will be Story 1.1 (repo scaffold + compose skeleton).` (drop `+ observability sidecars`).

### 4.6 Memory: project_bmad_books_backend_archetype.md

**File:** `~/.claude/projects/-Users-fralo-nearform-AINE-Training-BMAD-books/memory/project_bmad_books_backend_archetype.md`

- **Frontmatter `description:`** — drop `OTEL/Prometheus` from the locked-stack summary.
- **Body bullet at line 26 (Observability):** Replace with a sentence noting that, for BMAD_books specifically, the archetype's OTEL/Prometheus emission is treated as inert — the project does not deploy a collector, dashboards, or tracing backend. The OAuth/OIDC focus of the project does not benefit from the stack.
- **Implication #3 (Compose orchestration, line 38):** Drop the `merge that with` clause for the observability compose; the BMAD_books `docker-compose.yml` orchestrates Keycloak + SPA + BFF + RS + their volumes only.

### 4.7 ux-design-specification.md

**File:** `_bmad-output/planning-artifacts/ux-design-specification.md`

- **Line 173** — no change required. The sentence is a UX philosophy statement noting that observability lives in network/code rather than in the UI; it remains accurate (and arguably more so) after the stack is removed.

## 5. Implementation Handoff

**Scope classification:** Major (cross-cutting planning-artifact rewrite, but with zero implementation rollback because no story has been started).

**Recipient:** Single dev agent (this conversation) — applies all edits in batch.

**Success criteria:**

1. `grep -i -E "otel|observability|jaeger|prometheus|grafana|x-request-id" _bmad-output/planning-artifacts/*.md` returns only:
   - The PRD §12 Out-of-Scope addition (1 line in PRD.md).
   - The retained UX philosophy statement (line 173 of ux-design-specification.md).
   - The X-Request-Id reference in architecture.md, now attributed to a UUID middleware rather than OTEL.
2. `sprint-status.yaml` no longer contains `observability-sidecars` in any key.
3. The Story 1.1 spec, Stories 1.3 / 3.1 / 3.5 specs, and Story 5.4 smoke checklist all read coherently with no dangling references to removed sidecars or AR29.
4. Implementation-readiness report's "First implementation story will be Story 1.1" sentence matches the new Story 1.1 title.
5. The backend-archetype memory describes a project that uses the archetype's code patterns without deploying its observability sidecars.

**Handoff completes when** all edits above are applied to disk and the four checks in success-criteria pass.

---

**Approval:** Approved in advance by maintainer via /bmad-correct-course args on 2026-05-14 ("Remove observability entirely (most ambitious)"). User has also instructed: "work without stopping for clarifying questions." Proceeding to apply.
