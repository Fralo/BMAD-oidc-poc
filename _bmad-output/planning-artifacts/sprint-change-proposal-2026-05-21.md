---
title: Sprint Change Proposal — PKCE Removal + ACME-TS Principles Alignment
date: 2026-05-21
mode: incremental
scope_classification: major
author: Nearformer (via bmad-correct-course)
status: approved
related:
  - sprint-change-proposal-2026-05-19.md  # Epic 6 split (prior change)
  - architecture.md (Pattern Amendments)
  - epics.md (Story 1.5 amendment)
  - 1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md
---

# Sprint Change Proposal — 2026-05-21

## 1. Issue Summary

Two intertwined changes were requested in a single bmad-correct-course session on 2026-05-21:

1. **Remove PKCE from the Authorization Code flow.** The BFF is a confidential OAuth client and authenticates to Keycloak with a `client_secret`. PKCE (RFC 7636) was designed to protect public clients that lack a secret — a confidential client gains no incremental protection from adding PKCE on top. The POC originally enforced PKCE end-to-end (BFF generated `code_verifier`/`code_challenge`; Keycloak realm enforced S256). Removing it simplifies the flow without weakening it and brings the POC in line with the user's real-project (ACME-TS) auth posture.

2. **Audit the POC against eight ACME-TS auth design principles** (confidential client; BFF manages auth state; server-side session with opaque cookie; separation of authN/authZ; frontend → BFF only; discovery over hardcoding; fail-fast / default-deny; observability with structured decision logs) and propose changes for any divergences.

**Context.** The user is using this POC as a reference implementation for an upcoming ACME client engagement. The 5 of 8 principles that already match (confidential client, BFF-managed state, opaque cookie, FE→BFF only, fail-fast) need no change. The 3 that diverge (P4 separation of authN/authZ via BFF role mapping, P6 OIDC discovery bootstrap, P8 structured auth-decision logs) need targeted follow-up stories.

**Evidence.** ACME-TS principles list pasted into bmad-correct-course args. PKCE references at 14 code-tree locations plus four planning documents — full audit in §3 below.

## 2. Impact Analysis

### Epic impact

- **No epic is invalidated.** Epic 1 (FR-AUTH-01) is the home of OAuth login and is already `done`. Story 1.5 — which shipped PKCE — is amended in place: title updated, ACs annotated, implementation-artifact carries an amendment header. Status remains `done`.
- **New Epic 7 added** ("ACME-TS Principles Alignment") carrying three backlog stories (7.1 claim→role mapping, 7.2 OIDC discovery bootstrap, 7.3 structured auth-decision logs).
- **No epic-order changes.** Epic 7 is independent of Epics 1–6 and can be picked up at any time; nothing else depends on it.

### Story impact

- **Story 1.5 (done):** title, user-story line, and ~6 ACs amended to remove PKCE language; `pkce.py` deletion noted; tests rewired. The amendment is documented at the top of the implementation-artifact and in epics.md.
- **Stories 7.1 / 7.2 / 7.3 (new, backlog):** one per principles gap. Drafted with full ACs and source-file targets; ready to be picked up in a future sprint.

### Artifact conflicts

**PRD (`_bmad-output/planning-artifacts/PRD.md`):** 3 edits.
- §3 Goal 1 (was: "Authorization Code + PKCE flow with a confidential client") → reframed around the confidential-client / `client_secret` trust basis.
- §8 architectural constraint #2 (was: "Login uses Authorization Code flow with PKCE") → reframed around `client_secret_basic` auth; PKCE explicitly named as not-used.
- §12 out-of-scope: new bullet declaring PKCE deliberately omitted (defense-in-depth not in scope for this educational reference).

**Architecture (`_bmad-output/planning-artifacts/architecture.md`):** 10 edits across NFR block, cross-cutting concerns map, decisions A1 / A3, ErrorCode block (C5), Keycloak realm decision (I3), HTTP-status table (Format Patterns), the ASCII service-diagram caption, the Integration Points list, and the Validation Results paragraph. Plus a new **Pattern Amendments** subsection (per architecture.md's own rule at line 821 — pattern changes are appended there, not made by silent edit).

**Epics (`_bmad-output/planning-artifacts/epics.md`):** 18 edits across FR1, NFR2, AR2, AR7, AR9, AR27, Epic 1 narrative, Story 1.2 AC, Story 1.4 AC, Story 1.5 (title + 6 ACs), and the Epic 5 summary.

**Keycloak realm (`keycloak/realm-bmad-books.json`):** 2 edits — the `bmad-books-bff` client description and the removal of the `pkce.code.challenge.method: S256` attribute.

**Security review (`docs/security-review.md`):** 4 edits — the attestation-document framing, the `keycloak_cookie_session.py` description, the state-id cookie subsection, and the retirement of AR2 ("Plaintext PKCE `code_verifier`") as a no-longer-applicable accepted risk.

**BFF source code (`services/bff/src/bff/`):** 1 file deleted (`auth/pkce.py`); 4 files modified (`auth/keycloak_cookie_session.py`, `api/auth.py`, `services/session_service.py`, `models/entities/auth_state.py`). The `auth_states` table keeps its `code_verifier` column as nullable dead schema with model default `""` — no follow-up Alembic migration in this round (matches the "keep column, stop using" decision).

**BFF tests (`services/bff/tests/`):** 1 file deleted (`auth/test_pkce.py`); 5 files modified (`auth/synthetic_idp.py`, `auth/test_keycloak_cookie_session.py`, `models/entities/test_auth_state.py`, `services/test_session_service.py`, `api/test_auth.py`, `api/test_test_reset.py`). The synthetic IdP harness keeps the `code_verifier` kwarg on `stash_authorization_code(...)` as a no-op for backwards-compat with the many call sites that pass it.

**Story 1.5 implementation-artifact (`_bmad-output/implementation-artifacts/1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md`):** title amended; new amendment header explains the post-hoc PKCE removal and points readers to this proposal + architecture.md Pattern Amendments. Status remains `done`.

**Sprint status (`_bmad-output/implementation-artifacts/sprint-status.yaml`):** Epic 7 section added with three new story entries at `backlog`.

### Technical / operational impact

- **Compose:** no changes. Same five services, same ports, same healthchecks.
- **Keycloak admin UX:** unchanged. The `bmad-books-bff` client still works the same way; only the PKCE attribute is no longer set on the client.
- **Pre-seeded users / scopes / audience claim:** unchanged.
- **Coverage:** the `pkce.py` deletion drops two source lines from the coverage denominator; `test_pkce.py` deletion drops the corresponding test count. Per-file coverage targets are unaffected (all per-file thresholds are still met by the modified files).
- **E2E:** the Playwright J1 spec still exercises the real Keycloak login round-trip; the only observable difference is that the `/authorize` redirect URL no longer carries `code_challenge` / `code_challenge_method` query parameters.

## 3. Recommended Approach

**Selected option: Hybrid — direct adjustment + new Epic 7.**

The bmad-correct-course checklist evaluated three options:

1. **Direct adjustment** (modify in-place + delete `pkce.py`). Viable, low risk, medium effort.
2. **Rollback Story 1.5.** Not viable — Story 1.5 is the foundation of Epic 1 and rollback would unwind Epics 2–6.
3. **PRD MVP review.** Not viable — the change is a scope simplification, not a replan.

The selected **hybrid** combines option 1 (for PKCE removal, applied inline in this proposal as Groups A–H) with the addition of **Epic 7** carrying one story per principles-audit gap (P4, P6, P8). Rationale:

- PKCE removal is mechanical, reversible, and best done as direct surgical edits — applied inline.
- Principles-audit gaps are net-new feature work that benefit from being tracked as proper stories rather than smuggled into the PKCE-removal change. The user explicitly chose "create new stories in a follow-up epic" for the gap-handling question during the bmad-correct-course session.

## 4. Detailed Change Proposals

The edits applied in this session are organized into eleven groups, each approved individually during the interactive bmad-correct-course session. All eleven groups landed cleanly.

### Group A — PRD (`PRD.md`)

| # | Section | Change |
|---|---|---|
| A.1 | §3 Goal #1 | Replace "Auth Code + PKCE flow with a confidential client" with the confidential-client / `client_secret` framing. |
| A.2 | §8 Constraint #2 | Replace "Auth Code flow with PKCE" with `client_secret_basic` framing; name PKCE-omission explicitly. |
| A.3 | §12 Out-of-scope | Add bullet declaring PKCE deliberately out of scope. |

### Group B — Architecture (`architecture.md`)

10 edits including: NFR2 restatement (line 38), Cross-Cutting Concern #1, Decision A1 (BFF OIDC client library — also folds in the prior Story-1.5 `offline_access` scope correction), Decision A3 (renamed "PKCE verifier/state storage" → "OAuth state/nonce storage"), Decision C5 (`AUTH_STATE_INVALID` description), Decision I3 (Keycloak realm description), HTTP-status table, the ASCII service diagram, the Integration Points "BFF → Keycloak" line, the Validation Results confidence-level paragraph, and a new **Pattern Amendments** subsection with the 2026-05-21 entry.

### Group C — Epics (`epics.md`)

18 edits across FR1, NFR2, AR2, AR7, AR9, AR27, Epic 1 narrative, Story 1.2 AC, Story 1.4 AC, Story 1.5 (title + 6 ACs), and the Epic 5 summary line.

### Group D — Keycloak realm (`keycloak/realm-bmad-books.json`)

| # | Change |
|---|---|
| D.1 | Client description: now reads "Authorization Code flow with client_secret_basic; no PKCE (confidential client); no password grant." |
| D.2 | Removed `"pkce.code.challenge.method": "S256"` attribute from the `bmad-books-bff` client. |

### Group E — BFF source code

| # | File | Change |
|---|---|---|
| E.1 | `services/bff/src/bff/auth/pkce.py` | **Deleted.** |
| E.2 | `services/bff/src/bff/auth/keycloak_cookie_session.py` | Module docstring trimmed; `build_authorize_url(...)` drops the `code_challenge` parameter and the two PKCE entries from the query-param dict; `exchange_code(...)` drops `code_verifier`. |
| E.3 | `services/bff/src/bff/api/auth.py` | Import of `compute_code_challenge` removed; `/auth/login` unpacks a single value from `create_auth_state(...)` (no more tuple); `/auth/callback` calls `exchange_code(...)` without `code_verifier`; top-of-file flow docstring updated. |
| E.4 | `services/bff/src/bff/services/session_service.py` | `from bff.auth import pkce` import removed; `create_auth_state(...)` return type → `entities.AuthState` (was tuple); stops computing `code_verifier`. |
| E.5 | `services/bff/src/bff/models/entities/auth_state.py` | Docstring updated; `code_verifier: str = Field(default="", nullable=False)` — vestigial column kept with default-`""` so the existing NOT NULL constraint in 0001_init remains satisfied. |

No Alembic migration in this round — see "auth_states schema" decision recorded during the session.

### Group F — BFF tests

| # | File | Change |
|---|---|---|
| F.1 | `services/bff/tests/auth/test_pkce.py` | **Deleted.** |
| F.2 | `services/bff/tests/auth/synthetic_idp.py` | `_token_handler` drops `code_verifier` validation; `stash_authorization_code(...)` keeps `code_verifier` kwarg as backwards-compat no-op; response `scope` updated to `"openid reading-speed:read reading-speed:write"`. |
| F.3 | `services/bff/tests/auth/test_keycloak_cookie_session.py` | `build_authorize_url(...)` tests drop `code_challenge=`; assert `code_challenge` / `code_challenge_method` are absent from the URL; `exchange_code(...)` tests drop `code_verifier=`; the PKCE-mismatch test removed (redundant with `test_exchange_code_unknown_code_raises`). |
| F.4 | `services/bff/tests/api/test_auth.py` | `compute_code_challenge` import dropped; `_complete_login` helper no longer asserts the verifier round-trip; `test_auth_login_redirects_to_idp_with_pkce_params` renamed → `..._without_pkce_params` with inverted assertions; `test_auth_callback_pkce_mismatch_returns_400` renamed → `..._token_exchange_rejected_returns_400`. |
| F.5 | `services/bff/tests/models/entities/test_auth_state.py` | Docstring updated; `_build_auth_state` drops `code_verifier=`; the `code_verifier` NOT-NULL parametrize entry removed; `assert fetched.code_verifier == "verifier-1"` → `== ""`. |
| F.6 | `services/bff/tests/services/test_session_service.py` | Test renamed `..._persists_row_and_returns_verifier` → `..._persists_row`; tuple unpack removed; `code_verifier=` removed from two manual `AuthState` constructions. |
| F.7 | `services/bff/tests/api/test_test_reset.py` | `code_verifier="cv"` removed from the seeded AuthState row. |

### Group G — Security review (`docs/security-review.md`)

| # | Change |
|---|---|
| G.1 | Top-of-doc attestation paragraph: drops "PKCE verifier plaintext storage" from the list of accepted risks; adds a note that AR2 was retired. |
| G.2 | Implementing-code-paths line for `keycloak_cookie_session.py` reframed around `client_secret_basic` (no PKCE). |
| G.3 | State-id cookie subsection: row contents updated (`state`, `nonce`, `return_to`); vestigial `code_verifier` column noted. |
| G.4 | §AR2 ("Plaintext PKCE `code_verifier`") replaced with a brief "retired 2026-05-21" stub linking back to architecture.md Pattern Amendments. |

### Group H — Story 1.5 implementation-artifact

The story file `1-5-bff-cookie-session-oidc-plugin-pkce-synthetic-idp-test-harness.md` retains its filename for git history continuity but gains:
- A new H1 title with "(Authorization Code, no PKCE)" replacing "(PKCE)".
- An **Amendment 2026-05-21** callout at the top explaining the as-built behavior diverges from the original ACs and pointing readers to this proposal + architecture.md Pattern Amendments.
- Status unchanged at `done`.

### Group I — New Epic 7 stories

Three stories created at `_bmad-output/implementation-artifacts/`:
- `7-1-bff-claim-to-role-mapping-demo.md` — closes principle gap **P4**.
- `7-2-oidc-discovery-bootstrap.md` — closes principle gap **P6**.
- `7-3-structured-auth-decision-logs.md` — closes principle gap **P8**.

All three are status `backlog` and ready to be picked up in a future sprint.

### Group J — Sprint status (`sprint-status.yaml`)

Epic 7 block appended after Epic 6 with the three story entries at `backlog`. Story 1.5's status stays `done`.

### Group K — This proposal document.

## 5. Implementation Handoff

**Scope classification: Major** (touches PRD goal, NFR2, an already-done story, a new epic).

**Already-applied (no handoff needed):**

Groups A–J have all been applied inline during this bmad-correct-course session. The PKCE-removal side of the proposal is **complete as a code change**. No additional implementation effort is needed for the PKCE removal itself.

**Pending verification (recommended next steps):**

1. **Run the BFF test suite.** `cd services/bff && uv run pytest` — expect green; the deleted `test_pkce.py` reduces the test count by ~6, all other tests should pass.
2. **Run `docker compose up` and walk through J1.** The login flow should look identical to a human; only the network-layer query parameters differ (no `code_challenge` / `code_challenge_method` in the `/authorize` 302).
3. **Run the Playwright J1 spec.** `cd e2e && just e2e-up` — the spec should pass unmodified.
4. **Verify Keycloak realm import succeeds.** A `docker compose up keycloak --force-recreate` should complete realm import without warnings about the removed PKCE attribute.

**Future work (Epic 7, backlog):**

Stories 7.1 / 7.2 / 7.3 are drafted but not implemented. They close the three ACME-TS principles-audit gaps:

| Principle | Story | Effort | Risk |
|---|---|---|---|
| P4 — Separation of authN/authZ (BFF role mapping) | 7.1 | Small (single demo endpoint + realm group + Alembic migration) | Low |
| P6 — Discovery over hardcoding | 7.2 | Medium (config + startup hooks on both BFF and RS) | Low — well-trodden pattern |
| P8 — Observability — structured auth-decision logs | 7.3 | Medium (new helper + ~12 call-site conversions across BFF + RS) | Low |

Recommended sequence if you decide to implement Epic 7: **7.3 first** (the structured-log helper benefits the discovery work in 7.2), then **7.2**, then **7.1** (demo of P4 is independent of the others).

**Handoff agents (per bmad-correct-course routing):**

- **Architect (you):** review the architecture.md Pattern Amendments entry and confirm wording.
- **PM (you):** review PRD edits in §3 / §8 / §12.
- **Developer:** execute the verification steps above (#1 + #2 + #3 + #4); when Epic 7 is later picked up, implement 7.1 / 7.2 / 7.3 in fresh context windows (one story per session, fresh worktrees).

## Approval

Approved by Nearformer on 2026-05-21 via interactive bmad-correct-course session. All eleven groups (A–K) applied. Status of all touched documents and code: see §4 above for the file-level summary.
