---
status: review
story_key: 5-2-security-review-document
epic: 5
prerequisites: 1.1–1.14 (Epic 1 — Foundation, all done); 2.1–2.7 (Epic 2 — Books, all done); 3.1–3.6 (Epic 3 — Reading Speed, all done); 4.1–4.4 (Epic 4 — Estimate + Honest Failure, all done after 4.4 code-review pass on 2026-05-18); 5.1 (coverage audit, in review). The six PRD §9 topic implementations all landed and are test-pinned at baseline `3e3612a`.
created: 2026-05-18
baseline_commit: 3e3612a
---

# Story 5.2: Security review document

Status: review

<!-- Sprint: Epic 5 (Final Coverage Push & Security Review). Second story in Epic 5. -->
<!-- Follows: Story 5.1 (coverage audit + gap-fill — in review). Precedes: Story 5.3 (README polish + AI integration log). -->

## Story

As a reviewer evaluating the OAuth/OIDC reference,
I want a written security review at `docs/security-review.md` covering the six topics PRD §9 enumerates plus an explicit accepted-risk note for at-rest token storage,
So that the security posture is verifiable from the document and traceable to the implementing code paths and tests.

## Scope (read this first)

This is a **pure documentation story.** No production code changes, no new tests, no config edits. The deliverable is a single new file (`docs/security-review.md`) plus a one-line README reference. Every claim in the document must cite a code path that already exists at baseline `3e3612a` and (where applicable) a test that pins the behavior.

Why this scope: every one of the six PRD §9 topics has already been implemented and test-pinned across Epics 1–4. The security review is an **attestation document** that consolidates those decisions, traces them to code, names the accepted risks the architecture already documented, and enumerates the threats considered. It does NOT introduce new controls.

If, while writing, the developer surfaces a real security gap that wasn't captured by any prior story or defer (D1–D135 + D440–D442 + D470 in `deferred-work.md`), the correct response is:

- **Material risk that would change a reviewer's verdict** — STOP, raise it to the user, do not silently fix it inside this story. Story 5.2 is read-only on production code.
- **Documented accepted risk, RFC-compliance nit, or hardening-pass candidate** — name it in the "Known Gaps / Future Work" subsection (AC10) with its defer ID. Do not "fix on the way."

Concretely, this story delivers:

1. **`docs/security-review.md`** (NEW) — the security review document. Structure detailed in AC1–AC10.
2. **`README.md` reference** (MODIFY) — one line under an appropriate section pointing at `docs/security-review.md`. Mirror the placement convention Story 5.1 established for `docs/coverage-report.md` (line 26 of the current README).

Out of scope:

- **Story 5.1** (coverage audit at `docs/coverage-report.md`) — separate story. The review may reference 5.1's outputs (e.g., the line/branch coverage of `auth/` modules) but does not regenerate them.
- **Story 5.3** (README polish + AI integration log) — the README touch in this story is a single reference line; the full rewrite is 5.3's job.
- **Story 5.4** (final `docker compose up` smoke at `docs/smoke-run.md`) — separate story.
- **Any production code change.** D42 (PKCE verifier plaintext), D43 (PyJWT leeway), D63 (`WWW-Authenticate` header), D64 (leeway/nbf coverage), D67 (empty `sub` → 412), D71 (BFF `change-me` placeholder reject parity), D73 (Bearer case-sensitivity), D74/D85 (multi-bearer concat), D75 (router exposed via `__all__`), D79 (non-`AppException` envelope gap), D80 (refresh-rotation race), D81 (BFF `VALIDATION_ERROR` vs `invalid_input`), D83 (httpx `follow_redirects=False`), D84 (8-char id collision + `sub` cleartext logging), D440 (`BFF_CLIENT_SECRET` shared with Playwright runner), D441 (`_safe_session_id_log` newline sanitization), D442 (`session_not_found` envelope divergence), D470 (zero-width whitespace input validation), plus the CSP hardening + extra security headers (`X-Content-Type-Options`, `Referrer-Policy`, HSTS, etc.) all live in this story's **Known Gaps / Future Work** subsection (AC10), NOT in this story's diff. The document **names** them; it does not **close** them.
- **Penetration test or automated scan.** No `bandit`, `trivy`, `osv-scanner`, `npm audit`, or dependency-scanner output is required. The dependency hygiene point (PRD §9 topic 6) is satisfied by stating the chosen versions and their currency at the date of the report, not by running a scanner.
- **OWASP ASVS / NIST SSDF mapping.** PRD §9 names six specific topics; the document follows that structure verbatim. No formal framework cross-walk.
- **Threat-modeling formality** (STRIDE, LINDDUN, attack-tree diagrams). The "Threat Model Summary" subsection is **prose** — threat in one sentence, mitigation in one paragraph — per the epic AC at lines 1832–1841.

## Acceptance Criteria

### AC1 — `docs/security-review.md` exists with header, structure, and full topic coverage

**Given** the maintainer is at the repo root,
**When** the developer inspects `docs/security-review.md`,
**Then** the file exists, is non-empty, and follows this top-level structure:

```markdown
# Security Review — Reading Time Estimator

**Run date:** YYYY-MM-DD
**Commit SHA:** <full SHA or first 7 chars from `git rev-parse HEAD`>
**Reviewer:** <name or "BMAD capstone author">
**Scope:** OAuth2/OIDC + BFF + JWKS + scope-enforcement reference implementation (PRD §9 six-topic envelope).

## 1. Token storage and transport          ← AC2
## 2. Session cookie attributes            ← AC3
## 3. CSRF posture                         ← AC4
## 4. JWT validation correctness           ← AC5
## 5. Scope enforcement                    ← AC6
## 6. Standard SPA concerns                ← AC7
## Accepted Risks                          ← AC8
## Threat Model Summary                    ← AC9
## Known Gaps / Future Work                ← AC10
```

**And** the header records the date of the run (`Run date`) in ISO-8601 form (`YYYY-MM-DD`) and the commit SHA the run was made against (use `git rev-parse HEAD` at the moment of authoring — this should be the commit that holds the new file).
**And** the document is referenced from the README (see AC11).

### AC2 — §1 Token storage and transport

**Given** §1 of the document,
**When** the developer inspects it,
**Then** it covers, at minimum:

- **Where access, refresh, and id tokens live.** In the BFF's `sessions` SQLModel row — three columns `access_token`, `refresh_token`, `id_token` — stored in the BFF's SQLite file at `/data/bff.db` (named Docker volume).
- **Transport between SPA ↔ BFF.** An HttpOnly session cookie (`bmad_books_session_id` by default — actual name configurable via `BFF_SESSION_COOKIE_NAME`). No tokens, no JWTs, no JSON token payloads ever crossing into browser-accessible storage.
- **Transport between BFF ↔ RS.** `Authorization: Bearer <access_token>` header set by `ResourceServerClient` on every RS call. Refresh-and-replay on 401 (single retry).
- **Why this isolation matters.** The browser holds zero credential material that could be exfiltrated by XSS. The architectural constraint "Token isolation" (architecture line 76 / PRD §8) is the load-bearing rule.
- **Implementing code paths** (cite each):
  - `services/bff/src/bff/auth/keycloak_cookie_session.py` — Authorization Code + PKCE flow, token exchange, id-token verification, refresh and revocation.
  - `services/bff/src/bff/models/entities/session.py` — `sessions` SQLModel with `access_token` / `refresh_token` / `id_token` columns. (Note: the epic AC at line 1812 references `services/bff/src/bff/db/models/session.py` — the actual canonical path under archetype layout is `services/bff/src/bff/models/entities/session.py`. Cite the real path; this is the same file, the epic's source-hint was authored before the archetype path was finalized.)
  - `services/bff/src/bff/services/session_service.py` — session row CRUD + ID generation via `secrets.token_urlsafe(32)` (256-bit entropy).
  - `services/bff/src/bff/services/resource_server_client.py` — BFF → RS bearer-token plumbing + refresh-and-replay on 401.
- **Pin-test references** (cite each):
  - `services/bff/tests/auth/test_keycloak_cookie_session.py` (OIDC plumbing).
  - `services/bff/tests/services/test_session_service.py` (token persistence).
  - `services/bff/tests/services/test_resource_server_client.py` (bearer propagation + 401-refresh-replay).

### AC3 — §2 Session cookie attributes

**Given** §2 of the document,
**When** the developer inspects it,
**Then** it lists the exact session-cookie attributes shipped today:

- `HttpOnly` — yes (set in `services/bff/src/bff/api/auth.py` cookie-set call sites).
- `Secure` — environment-controlled by `BFF_SESSION_COOKIE_SECURE` (true in prod-shaped runs; false under the dev profile to allow `http://localhost`).
- `SameSite=Lax` — required to let the Keycloak post-callback redirect carry the cookie. `Strict` would not allow that redirect; architecture A4 (lines 350–354) is the authority on this trade-off.
- `Path=/` — applies to the entire BFF origin.
- **Opaque 256-bit value, not a JWT** — generated by `secrets.token_urlsafe(32)`; the session row is the source of truth. No business data encoded in the cookie.
- **Cookie names** — configurable via `BFF_SESSION_COOKIE_NAME` (default `bmad_books_session_id`) and `BFF_CSRF_COOKIE_NAME` (default `bmad_books_csrf_token`).

**And** it explicitly explains the `Lax`-vs-`Strict` rationale (post-callback navigation MUST carry the cookie or the auth code can't exchange against the session).
**And** it explicitly notes the **state-id cookie** (`bmad_books_auth_state_id`) used only during the OIDC login round-trip — also `HttpOnly`, `Max-Age=300` (5 minutes), `SameSite=Lax`, signed via `itsdangerous.URLSafeTimedSerializer` (architecture A3).
**And** it cites:

- `services/bff/src/bff/api/auth.py` (the cookie-set / cookie-clear call sites — lines 119–127 for clear, 155–165 for state cookie, 285–301 for session cookie set, with attribute kwargs explicit in each call).
- `services/bff/src/bff/auth/keycloak_cookie_session.py` (state-id signer + serializer at `state_id_serializer` / `sign_state_id` / `verify_state_id`).
- `services/bff/tests/auth/test_keycloak_cookie_session.py` (attribute assertions; the suite pins every `HttpOnly` / `SameSite` / `Secure` / `Path` value).

### AC4 — §3 CSRF posture

**Given** §3 of the document,
**When** the developer inspects it,
**Then** it describes the three-layered CSRF defense in this exact order:

1. **Double-submit cookie pattern** — BFF sets a NON-HttpOnly `bmad_books_csrf_token` cookie on session creation (the cookie is intentionally readable by JS so the SPA can echo it back as a header). The cookie value is an HMAC of the session's `csrf_secret` column (a separate per-session 256-bit secret distinct from the session id).
2. **Custom request header** — the SPA reads the cookie and sends `X-CSRF-Token: <value>` on every state-changing request (`POST`, `PUT`, `PATCH`, `DELETE`). BFF middleware compares header to cookie with `hmac.compare_digest` (constant-time).
3. **Origin/Referer check** — defense in depth. The middleware accepts the request only if `Origin` (preferred) or `Referer` (fallback) matches `settings.bff_base_url`.

**And** it explicitly enumerates the EXEMPT methods: `GET`, `HEAD`, `OPTIONS` — no CSRF token required. State-changing requests with a missing or mismatched token return `403 csrf_invalid` (per `ErrorCode.CSRF_INVALID` in `services/bff/src/bff/core/errors.py`).
**And** it explicitly notes the SPA interceptor that does the cookie→header echo: `spa/src/app/shared/http/csrf-interceptor.ts`.
**And** it cites:

- `services/bff/src/bff/auth/csrf.py` (middleware — exempt-methods, constant-time compare, Origin/Referer check).
- `services/bff/tests/auth/test_csrf.py` (one-to-one pin tests for: missing header → 403, mismatched header → 403, missing cookie → 403, missing Origin AND Referer → 403, exempt method bypass → no enforcement, both Origin and Referer valid → 200, etc.).
- `spa/src/app/shared/http/csrf-interceptor.ts` (and the colocated spec).

### AC5 — §4 JWT validation correctness

**Given** §4 of the document,
**When** the developer inspects it,
**Then** it covers, at minimum:

- **Library choice.** PyJWT (`pyjwt[crypto]`) on both services. Specific functions: `jwt.decode(...)` for verification, `jwt.PyJWKClient(...).get_signing_key_from_jwt(token)` for JWKS-cached key retrieval.
- **What is validated on every RS request.** `iss` (must equal `settings.oidc_issuer_url`), `aud` (must equal `settings.oidc_audience` = `bmad-books-resource-server`), `exp` (must be in the future at validation time), signature (against the cached JWKS key matching the token's `kid`). All four are required by `options={"require": ["iss", "aud", "exp", "sub"]}` (`services/resource-server/src/resource_server/auth/oidc_bearer.py:80–86`).
- **Why JWKS, not a hardcoded key.** Architecture line 80: "Public keys are not hardcoded." Key rotation at the IdP must not require redeploying the RS.
- **JWKS cache TTL behavior.** `PyJWKClient` is held at module scope and reused across requests. PyJWKClient does not expose a numeric TTL knob, but it transparently re-fetches the JWKS on a `kid` cache miss — which is the operational equivalent of TTL expiry plus key-rotation handling. Architecture line 415 mandates "TTL 24h with `kid`-rotation single-re-fetch" and the comment block at `oidc_bearer.py:43–48` documents the trade-off explicitly.
- **What is also validated, indirectly.** `nbf` (raises `ImmatureSignatureError` if present and in the future — PyJWT default behavior; caught and surfaced as `401 invalid_token`). `iat` is parsed but not range-checked.
- **The BFF id-token verification** (parallel implementation). `services/bff/src/bff/auth/keycloak_cookie_session.py:204–246` runs the same PyJWT/JWKS flow on the id_token coming back from `/token` at login.
- **Implementing code paths** (cite each):
  - `services/resource-server/src/resource_server/auth/oidc_bearer.py` — `_get_jwks_client`, `_validate_access_token`, `_principal_from_claims`, `require_scope`.
  - `services/bff/src/bff/auth/keycloak_cookie_session.py` — `_get_jwks_client`, `verify_id_token`.
- **Pin-test references**:
  - `services/resource-server/tests/auth/test_oidc_bearer.py` (covers: missing token, malformed header, wrong issuer, wrong audience, expired token, bad signature, key-rotation single-re-fetch, scope membership, empty scope set).
  - `services/bff/tests/auth/test_keycloak_cookie_session.py` (id-token side: bad signature, wrong issuer, expired id_token).

### AC6 — §5 Scope enforcement

**Given** §5 of the document,
**When** the developer inspects it,
**Then** it covers, at minimum:

- **Enforcement is on the RS, NOT the BFF.** This is architecture's "Scope-enforced computation" constraint (PRD §8 / architecture line 82). The BFF forwards the user's bearer token unchanged; scope decisions belong to the resource owner.
- **The two scopes.** `reading-speed:read` and `reading-speed:write`. Defined as **optional client scopes** in the Keycloak realm (`keycloak/realm-bmad-books.json`), granted to the `bmad-books-bff` confidential client, requested in the `scope` parameter at `/authorize` along with `openid offline_access`.
- **The per-endpoint scope table** (verbatim from architecture C3):

  | Method | Path | Required scope |
  |--------|------|----------------|
  | `GET` | `/v1/reading-speed` | `reading-speed:read` |
  | `PUT` | `/v1/reading-speed` | `reading-speed:write` |
  | `POST` | `/v1/estimate` | `reading-speed:read` |

- **The mechanism.** `require_scope("reading-speed:read")` / `require_scope("reading-speed:write")` FastAPI dependency factories in `services/resource-server/src/resource_server/auth/oidc_bearer.py:130`. Each decorated endpoint declares the required scope via `Depends(require_scope(...))`. Insufficient scope → `403 forbidden_scope`.
- **Why `require_scope` is a factory** (not a static dependency). Each endpoint declares its specific scope at definition time; the factory rejects empty / whitespace-padded scope strings at module load (intentional fail-fast at import, not request time).
- **What about identity?** Per architecture line 388, all RS endpoints read user identity from the JWT `sub` claim — no path or body identifier accepted for user. The BFF never injects `sub` into the body/path (architecture line 394); the RS reads `sub` only from the verified JWT.
- **Implementing code paths**:
  - `services/resource-server/src/resource_server/auth/oidc_bearer.py:130–155` (`require_scope` factory).
  - `services/resource-server/src/resource_server/api/reading_speed.py:32, 42` (per-endpoint scope deps).
  - `services/resource-server/src/resource_server/api/estimate.py:42` (per-endpoint scope dep).
  - `keycloak/realm-bmad-books.json` (the scope definitions + client mapping).
- **Pin-test references**:
  - `services/resource-server/tests/api/test_reading_speed.py` — scope happy paths + 403 scenarios.
  - `services/resource-server/tests/api/test_estimate.py` — scope happy paths + 403 scenarios.
  - `services/resource-server/tests/auth/test_auth_forbidden.py` — generic insufficient-scope coverage.

### AC7 — §6 Standard SPA concerns

**Given** §6 of the document,
**When** the developer inspects it,
**Then** it covers, at minimum:

- **Content-Security-Policy** — the BFF emits a CSP response header on every HTML response. The exact value (verbatim from `services/bff/src/bff/middleware/security_headers.py:17–21`):
  ```
  default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
  ```
  - Document the `style-src 'unsafe-inline'` carve-out (Tailwind v4 requires it; the architecture A8 accepts this trade-off).
  - Document the response-trigger rule (current behavior: CSP attached when the request carries `Accept: text/html` — see D369 in `deferred-work.md` for the design intent + the migration path to a response-`Content-Type`-driven approach).
- **No tokens reachable from JavaScript.** Restate the token-isolation contract from §1: the session cookie is HttpOnly; the only browser-readable cookie is the CSRF token (intentional, per the double-submit pattern); no access/refresh/id token ever leaves the server.
- **Output escaping.** Angular templates auto-escape by default. No `innerHTML` / `bypassSecurityTrustHtml` / `[innerHTML]` usage anywhere in the SPA. One-line statement + cite the convention.
- **Dependency hygiene.** State the chosen versions and their currency at the date of the report:
  - **Angular v21** (latest stable as of authoring).
  - **Tailwind CSS v4** (latest stable; the `@theme` block + `@import "tailwindcss"` syntax).
  - **Vitest 4.x + `@vitest/coverage-v8`** (test-time only).
  - **PyJWT (`pyjwt[crypto]`) ≥2.10** (RS + BFF).
  - **Authlib** (BFF, OIDC client) + **httpx** (BFF, async HTTP client for Keycloak + RS).
  - **FastAPI (latest) + SQLModel + Alembic + Pydantic v2** (archetype-pinned).
  - Note: no automated dependency scanner output is required (see Scope, "Out of scope"). The statement is "selected current stable versions at the report date; review when any of these reach EOL."
- **Implementing code paths**:
  - `services/bff/src/bff/middleware/security_headers.py` (CSP middleware).
  - `spa/angular.json` + `spa/package.json` (Angular 21 + Tailwind 4 toolchain).
  - `spa/src/styles.css` (Tailwind v4 `@theme` block — single CSS import).
- **Pin-test references**:
  - `services/bff/tests/middleware/test_security_headers.py` (CSP value byte-for-byte; attachment-trigger rule).

### AC8 — "Accepted Risks" subsection

**Given** a dedicated "Accepted Risks" subsection,
**When** the developer inspects it,
**Then** it explicitly calls out the following items, each as a named bullet with mitigation + production alternative + the architectural authority that accepted the risk:

1. **At-rest token storage in plaintext SQLite columns** (the primary accepted risk).
   - **Statement of the risk:** the BFF's `sessions` table stores `access_token`, `refresh_token`, `id_token` columns unencrypted in the SQLite file `/data/bff.db`.
   - **Mitigation:** the SQLite file lives in a named Docker volume (`bff_data`) not exposed to the host network; the BFF process is the only consumer; no host-side bind-mount.
   - **Production-deployment alternatives:** (a) application-level KEK (key-encryption-key) encrypting the three token columns; (b) move sessions to a dedicated encrypted store (e.g., Redis with envelope encryption); (c) replace persistent sessions with a JWE-encrypted session cookie that the BFF unwraps per-request (eliminates the at-rest concern entirely at the cost of cookie size).
   - **Authority:** architecture §"Operational Details" → "Token storage at rest" (lines 1362–1368). Out of scope per PRD §4 ("Production hardening beyond what the course's success criteria require").

2. **PKCE `code_verifier` stored plaintext in `auth_states` rows** (defer D42).
   - Same accepted-risk envelope as #1 (any process with DB read access can mount a successful token-exchange impersonation if it also intercepts the authorization code). Mitigation: same volume isolation; row deleted on callback; 5-minute TTL.

3. **No idle-session timeout beyond the refresh-token-expiry chain.**
   - Absolute timeout = Keycloak's refresh-token lifetime (30 days default). Idle timeout = the same — if the session is unused for longer than the refresh-token lifespan, the next request fails refresh and forces re-login. Production deployments would typically set tighter explicit idle tracking (e.g., 30-minute idle / 8-hour absolute) and Story 5.2 names this as accepted scope.
   - **Authority:** architecture §"Operational Details" → "Idle / absolute session timeout" (lines 1369–1373).

**And** each item explicitly cites the architecture line(s) that accepted the risk.

### AC9 — "Threat Model Summary" subsection

**Given** a "Threat Model Summary" subsection,
**When** the developer inspects it,
**Then** it enumerates the seven threats below, each with **one sentence** stating the threat and **one paragraph (2–4 sentences)** stating the mitigation:

1. **XSS in the SPA exfiltrates user tokens** — mitigated because no tokens are reachable from JavaScript at all (HttpOnly session cookie + server-side token storage), and CSP `script-src 'self'` prevents inline-script injection. Even a successful XSS gets only the user's browser session — not their refresh token. Reference: §1, §6 of this document.

2. **CSRF on BFF state-changing endpoints** — mitigated by the three-layer defense in §3: double-submit cookie + `X-CSRF-Token` header + `Origin`/`Referer` check. `SameSite=Lax` is an additional browser-level mitigation but the application-level checks are the load-bearing layer.

3. **Token replay after stealing the bearer in transit** — mitigated by short access-token lifetime (Keycloak default: 5 minutes; configurable) + TLS-everywhere assumption + refresh-token revocation on logout. A stolen bearer expires fast; a stolen refresh token is revoked at `/auth/logout`.

4. **Direct RS access bypassing the SPA flow** — **intentionally accepted.** The RS is a stateless OAuth resource server: anyone holding a valid bearer JWT with the correct `aud` (`bmad-books-resource-server`) and required scope can call it. This is the design — RS scope enforcement is the trust boundary, not RS "did the request come from the SPA". Reference: architecture §"BFF does not bypass the resource server" (line 83) and the broader OAuth contract.

5. **Scope escalation — a `reading-speed:read`-scoped token calling `PUT /v1/reading-speed`** — mitigated by RS-side scope enforcement (§5). The `require_scope("reading-speed:write")` dependency on the PUT handler returns `403 forbidden_scope` for any token missing that scope, regardless of the issuer's intent. Pinned by `tests/api/test_reading_speed.py` 403 scenarios. Reference: Story 3.2 (`oidc_bearer` plugin).

6. **Replay-after-logout — the user logs out, an attacker replays the captured refresh token** — mitigated by refresh-token revocation at Keycloak in the `/auth/logout` flow. The BFF calls Keycloak's revoke endpoint, then the `end_session_endpoint`, then clears the local session. Even if revoke fails (degrade-honestly contract), the local session is destroyed and the cookie is cleared, so the attacker can't reach the SPA's session-backed surface. Pinned by Story 1.13's J5 E2E spec (`e2e/tests/j5-logout.spec.ts`).

7. **Confused-deputy / `sub`-injection — the BFF injects a `sub` into the body or path, the RS trusts it** — mitigated by two architectural rules: (a) the BFF never injects `sub` into body/path (architecture line 394); (b) the RS reads `sub` ONLY from the verified JWT (`_principal_from_claims` in `oidc_bearer.py:89–98`). Pinned by Story 4.2 tests (the BFF's compute-estimate path passes only `pages`, never `sub`, to the RS).

**And** the subsection is prose — one sentence threat, one short paragraph mitigation. No tables, no formal STRIDE / LINDDUN mapping. The bar is: a reviewer can read this section in under 5 minutes and know which threats were considered and what defends against each.

### AC10 — "Known Gaps / Future Work" subsection

**Given** a "Known Gaps / Future Work" subsection,
**When** the developer inspects it,
**Then** it lists the items below as a numbered list. Each item is **one paragraph**: what it is, what the production-hardening equivalent looks like, the defer ID, and the severity from `deferred-work.md`.

The minimum content (all of these have explicit `Belongs to: Story 5.2` tags in `deferred-work.md`; they are surfaced HERE, not closed):

- **CSP hardening directives** — current CSP lacks `object-src 'none'`, `upgrade-insecure-requests`, `report-uri`/`report-to`, nonce-or-hash for scripts; `style-src 'unsafe-inline'` is permanent. Authority: architecture A8 + D371. Hardening pass adds nonce-based scripts, removes `'unsafe-inline'` via a Tailwind v4 nonce-injector, and wires a CSP-report collector.
- **Additional HTTP security headers** not yet attached: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security` (TLS-only deployments), `X-Frame-Options: DENY` (legacy fallback for `frame-ancestors`), `Permissions-Policy`, COOP/CORP/COEP. Authority: D372.
- **PyJWT `leeway` is 0 on both BFF and RS** — clock skew of 1–2 seconds causes spurious 401s. Authority: D43 (BFF) + D64 (RS). Hardening pass: `leeway=timedelta(seconds=10)` on both `jwt.decode` call sites.
- **`WWW-Authenticate: Bearer` header missing on RS 401 responses** — RFC 6750 §3 compliance gap. Authority: D63. Hardening pass: add the header to the `AppException` envelope for `SESSION_EXPIRED` / `invalid_token`.
- **Empty `sub` claim surfaces as 412 not 401** — the RS's defensive `claims.get("sub", "")` lets an RFC-permitted empty-string `sub` flow into the business layer instead of failing authentication. Authority: D67.
- **Refresh-token rotation race under concurrent BFF calls** — two parallel BFF requests around access-token expiry can clobber the rotated tokens and log the user out. Real production risk under HTTP/2 multiplexing or slow connections. Authority: D80.
- **`httpx.AsyncClient` defaults** — `follow_redirects=False` (latent prod-vs-dev ingress trap, D83); per-call connection pools defeat keep-alive (D82, performance-relevant).
- **Log hygiene** — `sub` is logged in cleartext on refresh attempts; session-id 8-char prefixes collide under load (birthday-paradox at ~thousands of sessions). PII concern in some jurisdictions. Authority: D84.
- **Bearer / Authorization header parsing** — case-sensitive `Bearer ` (D73), multi-bearer concat undetected (D74 RS, D85 BFF). RFC 6750 §2.1 + RFC 9110 §5.3 alignment.
- **`bff.api.test_reset.register_test_reset_router` does not reject `TEST_RESET_TOKEN=change-me`** — placeholder defense-in-depth parity with the RS half. Authority: D71.
- **`router` exposed via `__all__` in test_reset modules** — future maintainer who imports `router` directly bypasses the gate helper. Authority: D75. Hardening pass: rename to `_router`, drop from `__all__`.
- **Non-`AppException` exceptions bypass the project error envelope** — bare DB-driver `OperationalError` propagates as `text/plain "Internal Server Error"`. Authority: D79.
- **BFF `validation_exception_handler` emits archetype-default `VALIDATION_ERROR` (upper-snake) instead of project-standard `invalid_input`** — wire-code drift between BFF and RS. Authority: D81.
- **Health endpoint amplification** — per-request engine setup + outbound httpx to OIDC + no rate-limit window allows ~5 outbound discovery requests/sec from one source. Authority: D25.
- **`BFF_CLIENT_SECRET` shared between production confidential client and the Playwright runner** — test artifacts could capture the credential. Clean fix: a separate `bmad-books-bff-test` confidential client used only under the `e2e` profile. Authority: D440.
- **Log-injection vector — `_safe_session_id_log` does not sanitize newline/control chars in `sub`** — a maliciously-shaped JWT `sub` (RFC 7519 forbids, BFF doesn't validate) could log-split. Authority: D441.
- **`session_not_found` envelope is shape-distinct from auth-failure 401** — minor probe side-channel after deeper compromise. Authority: D442.
- **Input validation — zero-width / BOM characters pass `_strip_and_reject_blank`** — a "whitespace-only" title made of U+200B / U+FEFF / U+2060 persists as a visually-empty row. Authority: D470.
- **No GitHub Actions CI workflow** — local-only test gates today. PRD §4 / architecture I7 out-of-scope per project charter. Real production setups add lint + tests + docker build + Playwright run in CI.

**And** every entry cites its defer ID so a maintainer can navigate to the full description in `_bmad-output/implementation-artifacts/deferred-work.md`.

### AC11 — README references `docs/security-review.md`

**Given** the security review at `docs/security-review.md` exists,
**When** the developer updates `README.md`,
**Then** the README contains exactly one reference line to `docs/security-review.md`, placed alongside the existing `architecture.md` and `docs/coverage-report.md` references in the "Architecture overview" section (current README lines 22–26).

**Notes:**
- Do NOT rewrite the README in this story. Story 5.3 owns the full rewrite. The reference here is one line so 5.3 has minimal churn.
- Mirror Story 5.1's reference-line style. Current README line 26 reads: `` See [`docs/coverage-report.md`](docs/coverage-report.md) for the per-surface coverage snapshot and thresholds. ``
- This story's reference: `` See [`docs/security-review.md`](docs/security-review.md) for the OAuth/OIDC security review (PRD §9 envelope: token storage, cookie attributes, CSRF, JWT validation, scope enforcement, SPA concerns). ``
- Acceptable placements: directly after the existing `docs/coverage-report.md` line, OR appended as a third sibling under the "Architecture overview" heading. Single line; no new section.

## Tasks / Subtasks

- [x] **Task 1 — Verify implementing code paths still exist at baseline `3e3612a` (AC2–AC7)**
  - [x] 1.1 All BFF / RS / SPA / Keycloak source paths verified at baseline `3e3612a`. Confirmed: `auth/keycloak_cookie_session.py` (all five named symbols present); `auth/csrf.py` (exempt methods at line 32, `hmac.compare_digest` at line 91, Origin/Referer logic 101–135, `_origin_matches` userinfo-rejection at 169–170); `auth/pkce.py` exists; `middleware/security_headers.py` CSP value verbatim at lines 17–21 — quoted byte-for-byte into the document; `models/entities/session.py` (canonical archetype path; epic AC's `db/models/session.py` is stale source-hint — document cites the actual path with a parenthetical correction); all three RS endpoint files exist with the correct scope deps (`reading_speed.py:32` → `reading-speed:read`, `reading_speed.py:42` → `reading-speed:write`, `estimate.py:42` → `reading-speed:read`); `realm-bmad-books.json` exists with bff client + scopes; `spa/src/app/shared/http/csrf-interceptor.ts` exists.
  - [x] 1.2 All test files exist: `tests/auth/test_keycloak_cookie_session.py`, `test_csrf.py`, `test_pkce.py`; `tests/middleware/test_security_headers.py`; `tests/services/test_session_service.py`, `test_resource_server_client.py`; RS `tests/auth/test_oidc_bearer.py`, `test_auth_forbidden.py`, `test_auth_unauthorized.py`; `tests/api/test_reading_speed.py` (scope-tagged tests at lines 76 + 136 verified), `test_estimate.py`.
  - [x] 1.3 One path-shift recorded: epic AC line 1812 cites `services/bff/src/bff/db/models/session.py`; actual canonical archetype path is `services/bff/src/bff/models/entities/session.py`. Document cites the actual path with a parenthetical correction note inline. No other line-range shifts beyond the minor CSRF / api/auth.py line numbers re-verified during authoring.

- [x] **Task 2 — Author `docs/security-review.md` skeleton + topic sections (AC1–AC7)**
  - [x] 2.1 Created `docs/security-review.md` with header (Run date 2026-05-18, Commit SHA `3e3612a` (worktree baseline), Reviewer "BMAD capstone author", Scope statement naming PRD §9 + the three subsections).
  - [x] 2.2 §1 Token storage and transport authored: token columns + 256-bit session ID + cookie transport + bearer transport + refresh-and-replay + `repr=False` log-leak defense; all four code paths cited; all three pin-test files cited.
  - [x] 2.3 §2 Session cookie attributes authored: attribute table + SameSite=Lax rationale + state-id cookie sidebar (signed `URLSafeTimedSerializer` reference + 5-minute window) + CSRF cookie deliberate-non-HttpOnly sidebar; cite cookie set/clear call sites at `api/auth.py:158–166`, `285–305`, `307–314`, `119–129`.
  - [x] 2.4 §3 CSRF posture authored: three-layer defense (method exempt + double-submit + Origin/Referer) + constant-time `hmac.compare_digest` + SPA interceptor + `/v1/test/reset` exemption note; cites `csrf.py:32`, `73–99`, `101–135`, `_origin_matches:159–173`.
  - [x] 2.5 §4 JWT validation correctness authored: PyJWT library + step-by-step validation list (`kid` lookup, algorithm pinning, audience, issuer, `exp`, required-claims gate) + JWKS cache + BFF id-token parallel including the D2/D8 browser-URL caveat + nonce binding; cites `oidc_bearer.py:52`, `76`, `96`, `118`, `130` and `keycloak_cookie_session.py:196`, `204`.
  - [x] 2.6 §5 Scope enforcement authored: enforcement-at-RS rule + scope grant table + per-endpoint scope table + `require_scope` factory module-load fail-fast + sub-from-JWT-only rule + the BFF_CLIENT_SECRET-sharing follow-up reference; cites `oidc_bearer.py:130`, `reading_speed.py:32, 42`, `estimate.py:42`, `realm-bmad-books.json`.
  - [x] 2.7 §6 Standard SPA concerns authored: CSP byte-for-byte + directive-by-directive table + attachment rule + `style-src 'unsafe-inline'` carve-out + additional-headers gap note; Angular auto-escape + no `bypassSecurityTrust*` / `innerHTML` / `eval` grep result; dependency hygiene version table with currency-as-of-2026-05-18; CSP middleware + Tailwind `@theme` + Angular toolchain cites.

- [x] **Task 3 — Author "Accepted Risks" subsection (AC8)**
  - [x] 3.1 Three items in required order: AR1 plaintext token storage; AR2 plaintext PKCE `code_verifier`; AR3 no idle-session timeout beyond refresh chain.
  - [x] 3.2 Each item carries: statement of risk + mitigation + production alternatives (with explicit options for AR1: KEK + dedicated encrypted store + JWE cookie) + architecture-line citation (`:1362–1368` for AR1; D42 for AR2; `:1369–1373` for AR3).

- [x] **Task 4 — Author "Threat Model Summary" subsection (AC9)**
  - [x] 4.1 Seven threats in required order: T1 XSS, T2 CSRF, T3 token replay, T4 direct RS access (intentionally accepted), T5 scope escalation, T6 replay-after-logout, T7 confused-deputy.
  - [x] 4.2 Each threat is one sentence + one short paragraph mitigation. Pins cited inline: §1+§6 (T1), §3 (T2), Story 3.5 ResourceServerClient + Story 1.13 J5 (T3), architecture line 82+83 (T4), `tests/api/test_reading_speed.py:76,136` (T5), Story 1.13 J5 (T6), `tests/services/test_resource_server_client.py::test_compute_estimate_*` + Story 3.3 / 4.1 RS-side tests (T7).
  - [x] 4.3 Prose-only — no STRIDE / LINDDUN matrix. No tables.

- [x] **Task 5 — Author "Known Gaps / Future Work" subsection (AC10)**
  - [x] 5.1 Cross-walked the 19 listed items against `deferred-work.md`. All defer IDs confirmed accurate at time of authoring: D371 (CSP hardening), D372 (extra headers), D43+D64 (PyJWT leeway), D63 (WWW-Authenticate), D67 (empty `sub`), D80 (refresh race), D82+D83 (httpx defaults), D84 (log hygiene), D73+D74+D85 (Bearer parsing), D71 (BFF change-me parity), D75 (router via `__all__`), D79 (non-AppException), D81 (BFF VALIDATION_ERROR drift), D25 (health amplification), D440 (BFF_CLIENT_SECRET shared), D441 (log-injection), D442 (session_not_found envelope), D470 (zero-width whitespace), no-CI item. The minimum-18 floor in the AC is exceeded (19 items).
  - [x] 5.2 Each item: one paragraph describing the gap + production-hardening equivalent (where applicable) + defer-ID citation + severity from `deferred-work.md`.
  - [x] 5.3 NO new defers logged here. Task 8.1 confirms zero new defers surfaced.

- [x] **Task 6 — Add README reference line (AC11)**
  - [x] 6.1 Read `README.md` — current state is 31 lines (worktree-baseline; 5.1 added the coverage-report line at line 26).
  - [x] 6.2 Added the required reference line directly after the existing `docs/coverage-report.md` reference, mirroring its style. The new README is 33 lines.
  - [x] 6.3 No other README changes.

- [x] **Task 7 — Regression sweep (DoD)**
  - [x] 7.1 `git status --short` shows: ` M README.md`, ` M sprint-status.yaml`, `?? 5-1-coverage-audit-gap-fill.md` (synced from parent), `?? 5-2-security-review-document.md` (this story), `?? docs/` (coverage-report.md from 5.1 + the new security-review.md). No production source / test / compose / Justfile / keycloak / planning-artifact changes.
  - [x] 7.2 N/A — no production code was touched. (The worktree was synced from the parent before dev work began so the 5-1 deliverables + sprint-status.yaml + README's coverage-report line are present as baseline; the dev-pass only added `docs/security-review.md` + the one README line + this story file's status fields + the sprint-status flip.)
  - [x] 7.3 Markdown lint sanity: 28 code fences = 14 balanced code blocks; 9 H2 sections matching the AC1 structure (Token storage / Cookie attributes / CSRF / JWT validation / Scope enforcement / Standard SPA concerns / Accepted Risks / Threat Model Summary / Known Gaps); 31 relative `../*` links all resolve to existing repo files (verified via Python `os.path.exists` walk).

- [x] **Task 8 — Capture deferred items (DoD)**
  - [x] 8.1 Zero new defers logged. Task 1's verification surfaced no security gap that wasn't already in `deferred-work.md`. One language-version observation noted (Python 3.14 parses and runs `except ValueError, TypeError:` in `services/bff/src/bff/auth/csrf.py:103` — the existing behavior catches both exceptions correctly per BFF test pass on the latest baseline, so this is not a security defect and not in scope for this story to "fix on the way").
  - [x] 8.2 Confirmed — the expected zero-new-defer path was taken. AC10's consolidation of 19 existing defers is what the security review surfaces.

## Files this story creates / modifies

**Created:**
- `docs/security-review.md` — the security review document (Task 2 + 3 + 4 + 5).

**Modified (always):**
- `README.md` — one reference line to `docs/security-review.md` (Task 6).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `5-2-security-review-document` status transitions `ready-for-dev` → `in-progress` → `review` → (after code review) `done`. `epic-5` stays `in-progress` (already transitioned by Story 5.1).
- `_bmad-output/implementation-artifacts/5-2-security-review-document.md` (this file) — Tasks/Subtasks checkboxes marked; Dev Agent Record filled; Change Log entries added.
- `_bmad-output/implementation-artifacts/deferred-work.md` — append "Deferred from: dev of 5-2-..." section IF Task 8 surfaces items (expected: none).

**Files this story explicitly does NOT touch:**
- `services/bff/src/**` / `services/resource-server/src/**` / `spa/src/**` — this is a doc-only story. No production code changes. (See "Scope" — material new risks STOP the story and raise to the user; documented-accepted-risk and nit items go in AC10's section.)
- `services/bff/tests/**` / `services/resource-server/tests/**` / `spa/src/**/*.spec.ts` / `e2e/**` — no new or modified tests.
- `compose/**`, `docker-compose.yml`, `Justfile`, `keycloak/**` — no infra changes.
- `_bmad-output/planning-artifacts/**` — planning docs are frozen.
- `services/resource-server/CLAUDE.md` — RS agent rules; read-only context.
- `docs/coverage-report.md` — owned by Story 5.1, in review.

## Failure-prevention checklist

1. **Do NOT fix a defer in this story.** Every D-number cited in AC10 is in scope only as a **named, documented gap** — not as a code change. Story 5.2's diff is doc-only. If the developer is tempted to "just fix the easy one" (e.g., add `X-Content-Type-Options: nosniff`), the story is suddenly a multi-component refactor with no test coverage planned. Defer is the answer.
2. **Do NOT invent new defers casually.** AC10 consolidates the existing ones (D1–D135 + D440–D442 + D470 + the CSP / extra-headers items). A new finding must clear two bars before it goes in Task 8.1: (a) it isn't already in `deferred-work.md` under any number; (b) it's a real risk, not a rephrasing of one already captured.
3. **Do NOT cite stale paths.** The epic AC at line 1812 cites `services/bff/src/bff/db/models/session.py`; the actual canonical path is `services/bff/src/bff/models/entities/session.py` (archetype layout). Task 1.1 catches this; cite the **actual** path. Same vigilance applies to any line-range citation — line numbers shift as files evolve; verify before quoting.
4. **Do NOT quote the CSP string by hand.** Read `services/bff/src/bff/middleware/security_headers.py:17–21` and copy the literal bytes. A typo in the document (e.g., dropping `frame-ancestors 'none';`) is a real-world danger that future maintainers might cargo-cult into the actual middleware.
5. **Do NOT lower a stated severity.** If `deferred-work.md` rates D80 as "medium" (real prod scenario), the AC10 entry MUST NOT soften that to "low" or omit the severity. The defer-tracking file is the authority.
6. **Do NOT add an OWASP ASVS / STRIDE / NIST SSDF cross-walk.** PRD §9's envelope is the six topics enumerated there. A formal framework mapping is out of scope per the "Scope" section above; it would push the doc to 10× its target length and add a maintenance burden no one in this project will pay.
7. **Do NOT run automated scanners.** `bandit`, `trivy`, `npm audit`, `osv-scanner` outputs are not required — the dependency hygiene point is a "selected current stable versions" statement, not a CVE roll-up. Adding scanner output would (a) age fast, and (b) implicate a "what should we do about CVE-X" decision the project hasn't budgeted.
8. **Do NOT rewrite the README.** AC11 is one line, mirroring the placement convention Story 5.1 set up at README line 26. Story 5.3 owns the full rewrite.
9. **Do NOT commit a TODO or "fill in later" placeholder.** Every section reaches the AC's "minimum content" bar before the story moves to review. A partial doc is a failed Story 5.2.
10. **Do NOT omit the threat model just because it's prose-heavy.** Reviewers expect to scan AC9 and see seven named threats with one-paragraph mitigations. Less than seven means the AC fails. More than seven is fine — the seven listed are the floor.
11. **Do NOT cite secrets in the document.** Specifically: no `KEYCLOAK_ADMIN_PASSWORD`, no `BFF_CLIENT_SECRET`, no `TEST_RESET_TOKEN` — even the placeholder `change-me`. Cite the env-var NAMES and where they're configured (`.env.example`, `compose/app.e2e.yml`); never the values.
12. **Do NOT cite the PKCE code_verifier or any session-table column value.** Same rule as #11 — name the column, name the encryption-at-rest gap, never display sample data.
13. **Do NOT confuse "accepted risk" with "known gap".** AC8's three items are decisions architecture made and PRD §4 ratified (production hardening is out of scope). AC10's items are real concerns the project has not addressed and that a production deployment would. The distinction matters; reviewers may grade the project on whether it understood which is which.
14. **Do NOT modify Story 5.1's README reference line.** It's at README line 26, was just added by Story 5.1, and the placement convention is what this story mirrors. Touching it would break the visible "X follows Y added Z" intent.

## Dev Notes

### Architecture and code constraints relevant to this story

- **PRD §9's six-topic envelope is the load-bearing contract.** Quote: "A documented security review covering at minimum: token storage and transport, session cookie attributes, CSRF posture, JWT validation correctness, scope enforcement, and standard SPA concerns (XSS, injection)." (PRD line 90; restated in architecture line 47.) The document's six top-level sections map 1-to-1 to those six topics, in that order. Reordering or merging sections is a contract break.
- **Architecture A1–A8** (lines 343–354) — the eight load-bearing auth/security decisions. The document cites these by section name + line number where each decision was made:
  - A1 (Authlib + cookie-session OIDC plugin) → §1.
  - A2 (PyJWT + PyJWKClient) → §4.
  - A3 (server-side `auth_state` row + signed state-id cookie) → §2 sidebar.
  - A4 (HttpOnly + Secure + SameSite=Lax + opaque 256-bit) → §2.
  - A5 (double-submit + Origin/Referer) → §3.
  - A6 (reactive refresh-on-401) → §1 transport.
  - A7 (revoke + end-session + clear) → §9 threat 6.
  - A8 (CSP) → §6.
- **Token isolation invariants** (architecture lines 76–82):
  - "Access and refresh tokens must never be transmitted to, stored in, or accessible from the SPA or any browser-accessible storage" — §1 + §6 enforce this.
  - "JWKS-based validation. The resource server validates JWTs by fetching and caching the authorization server's JWKS. Public keys are not hardcoded" — §4.
  - "Identity source of truth. No service other than the authorization server stores user account records. User-owned data on the BFF and resource server is keyed by the `sub` claim" — §5 (sub-from-JWT-only) + §9 threat 7 (confused-deputy mitigation).
- **Architecture §Operational Details — Token storage at rest** (lines 1362–1368) — explicitly mandates that the security review call out the plaintext token columns as accepted risk. This is the AC8 #1 anchor.
- **Architecture §Operational Details — Idle / absolute session timeout** (lines 1369–1373) — the AC8 #3 anchor.

### Source-of-truth code paths (cite EXACTLY these in the document)

**BFF security surface:**

| Topic | File | Key symbols / lines |
|-------|------|---------------------|
| OIDC client + PKCE + state cookie + revoke + end-session + id-token verify | `services/bff/src/bff/auth/keycloak_cookie_session.py` | `state_id_serializer:51`, `sign_state_id:56`, `verify_state_id:61`, `build_authorize_url:89`, `exchange_code:147`, `_get_jwks_client:196`, `verify_id_token:204`, `revoke_refresh_token:247`, `end_session:280` |
| CSRF middleware | `services/bff/src/bff/auth/csrf.py` | exempt methods (GET/HEAD/OPTIONS) at top; `hmac.compare_digest` at line 91; `csrf_token_mismatch` log at line 95; Origin/Referer logic at lines 74–115 |
| CSP middleware | `services/bff/src/bff/middleware/security_headers.py` | `_CSP_VALUE` at lines 17–21; attachment at line 38 |
| Cookie-set / cookie-clear call sites | `services/bff/src/bff/api/auth.py` | session clear @119–127; state cookie set @155–165; session cookie set/clear @285–301 |
| Session SQLModel | `services/bff/src/bff/models/entities/session.py` | `access_token`, `refresh_token`, `id_token`, `csrf_secret`, `expires_at` columns |
| AuthState SQLModel (PKCE verifier storage) | `services/bff/src/bff/models/entities/auth_state.py` | `code_verifier`, `state`, `nonce`, `return_to` columns |
| Session service (CRUD + 256-bit ID generation) | `services/bff/src/bff/services/session_service.py` | `create_session`, `create_auth_state`, retry-on-IntegrityError pattern |
| BFF→RS bearer client + refresh-replay | `services/bff/src/bff/services/resource_server_client.py` | `_do_rs_call`, `_refresh_access_token` (lines 178–224) |
| Error envelope codes | `services/bff/src/bff/core/errors.py` | `ErrorCode.SESSION_EXPIRED`, `CSRF_INVALID`, `FORBIDDEN_SCOPE`, `RESOURCE_SERVER_UNAVAILABLE` |
| Test-reset endpoint (e2e-gated) | `services/bff/src/bff/api/test_reset.py` | gated by `ENABLE_TEST_RESET` + bearer `TEST_RESET_TOKEN` |

**RS security surface:**

| Topic | File | Key symbols / lines |
|-------|------|---------------------|
| OIDC bearer + JWKS + scope factory | `services/resource-server/src/resource_server/auth/oidc_bearer.py` | `_get_jwks_client:52`, `_validate_access_token:79–87` (decode options `require=["iss","aud","exp","sub"]`), `_principal_from_claims:89–98`, `require_scope:130` factory + module-load fail-fast at 133–141 |
| Per-endpoint scope deps | `services/resource-server/src/resource_server/api/reading_speed.py` | GET handler @32 (`reading-speed:read`); PUT handler @42 (`reading-speed:write`) |
| Estimate scope dep | `services/resource-server/src/resource_server/api/estimate.py` | POST handler @42 (`reading-speed:read`) |
| Role mapping (archetype extension) | `services/resource-server/src/resource_server/auth/role_mapping.py` | `RoleMappingProvider` subclass — basis of scope enforcement |
| Test-reset endpoint (e2e-gated) | `services/resource-server/src/resource_server/api/test_reset.py` | gated by `ENABLE_TEST_RESET` + bearer `TEST_RESET_TOKEN`; includes `_PLACEHOLDER_TOKEN` reject (defense-in-depth parity per D71 future-work item) |
| Error envelope codes | `services/resource-server/src/resource_server/core/errors.py` | `ErrorCode.FORBIDDEN_SCOPE`, `READING_SPEED_UNSET`, mirror of project enum |

**SPA security surface:**

| Topic | File | Notes |
|-------|------|-------|
| CSRF echo interceptor | `spa/src/app/shared/http/csrf-interceptor.ts` | Reads `bmad_books_csrf_token` cookie, sets `X-CSRF-Token` header on POST/PUT/PATCH/DELETE |
| HttpClient cookie credentials | `spa/src/app/app.config.ts` | `provideHttpClient(withFetch())` + `withInterceptors([authInterceptor, csrfInterceptor])`; the `withCredentials: true` is provided by the SPA's interceptor wiring per architecture §F |
| Tailwind v4 design tokens | `spa/src/styles.css` | `@theme` block — the `style-src 'unsafe-inline'` carve-out in CSP exists because Tailwind v4 emits inline styles from this block |
| AuthService (login/logout/session-fetch) | `spa/src/app/auth/auth-service.ts` | The SPA's view onto the BFF's auth surface; no token handling |

**Keycloak realm:**

| Topic | File | Notes |
|-------|------|-------|
| Realm + clients + scopes + audience mapper | `keycloak/realm-bmad-books.json` | `bmad-books` realm; `bmad-books-bff` confidential client; optional client scopes `reading-speed:read` + `reading-speed:write`; audience mapper `aud-resource-server` (closes D2 issue 2 per architecture line 493) |

### Source-of-truth test paths (cite EXACTLY these where AC2–AC7 require pin-tests)

**BFF tests** (under `services/bff/tests/`):

- `auth/test_keycloak_cookie_session.py` — OIDC plumbing, state cookie attrs, id-token verify (iss/aud/exp/signature), state-cookie expiry.
- `auth/test_csrf.py` — exempt-method bypass, missing/mismatched header, missing/mismatched cookie, missing Origin & Referer, Origin valid + Referer absent, Referer fallback when Origin missing, constant-time compare boundaries.
- `auth/test_pkce.py` — PKCE verifier generation + S256 challenge derivation.
- `middleware/test_security_headers.py` — CSP value byte-for-byte; attachment-trigger rule (request-`Accept`-driven per current behavior; see D369 for the response-`Content-Type`-driven migration item).
- `services/test_session_service.py` — session row CRUD; PK collision retry path (D38 resolution).
- `services/test_resource_server_client.py` — bearer propagation, 401-refresh-replay, refresh failure → `RsSessionTerminated` + cookie clear, empty-body 503, `RsUnavailable` for 5xx/timeout.
- `api/test_auth.py` — `/auth/login` 302, `/auth/callback` token-exchange, `/auth/logout` revoke + end-session + clear.
- `api/test_me.py` — `/api/me` 200 / 401 envelope.
- `api/test_test_reset.py` — gate-off → 404; gate-on + bearer-correct → 204; gate-on + bearer-wrong → 401.
- `observability/test_secret_redaction.py` — log-line redaction patterns.

**RS tests** (under `services/resource-server/tests/`):

- `auth/test_oidc_bearer.py` — JWKS happy + key-rotation refetch; iss/aud/exp/signature negative scenarios; missing/empty scope; `require_scope` factory module-load fail-fast.
- `auth/test_auth_forbidden.py` — generic 403 forbidden_scope coverage.
- `auth/test_auth_unauthorized.py` — generic 401 invalid_token coverage.
- `auth/test_role_mapper.py` + `test_role_mapping_providers.py` + `test_require_role_uses_mapper.py` — archetype extension points.
- `api/test_reading_speed.py` — GET/PUT happy paths + `*_scope_*` 403 scenarios + 412 unset.
- `api/test_estimate.py` — POST happy paths + `*_scope_*` 403 scenarios + 412 unset.
- `api/test_test_reset.py` — same gating contract as BFF.

**SPA tests** (under `spa/src/app/`):

- `shared/http/csrf-interceptor.spec.ts` — cookie-→-header echo + case-handling + method matrix.
- `shared/http/auth-interceptor.spec.ts` — 401 → bounce-to-login flow.

### Previous-story intelligence

- **From Story 5.1 (immediate predecessor):**
  - The "doc + README reference line" pattern is the precedent. Story 5.2 mirrors it: one new `docs/<name>.md` + one README line under "Architecture overview." Do NOT introduce a new README section.
  - Story 5.1's README placement is at line 26 (verified by Read above). This story appends one line directly after.
  - The audit-host has no `just` binary (Story 5.1 dev note). Irrelevant for Story 5.2 — there's no compose/e2e run in this story — but worth knowing if a Task 1 verification step ever wants to spot-check the runtime.
- **From Story 4.4 (most recent code-bearing story):**
  - The Justfile's `e2e-up` recipe and the `--build` flag are load-bearing for the e2e profile (referenced in the security review's §1 transport discussion via the `compose/app.e2e.yml` overlay).
  - No SPA / BFF / RS production code changed at 4.4 — the security surface as of `3e3612a` is exactly what landed at story 4.3's merge (commit `bb15aca`).
- **From Story 1.6 (CSRF middleware + CSP header — the security-surface origin commit):**
  - The CSP value is byte-mandated by architecture A8. Story 1.6's test (`middleware/test_security_headers.py`) pins it byte-for-byte. Document quotes it; doesn't paraphrase.
  - The CSP attachment-trigger rule is request-`Accept`-driven per Story 1.6 AC8 (mandatory). D369 documents the migration path to a response-`Content-Type`-driven approach for future SSR; AC10 captures this.
- **From Story 1.5 (OIDC plugin):** D43 (PyJWT leeway=0) — captured in AC10 of this story.
- **From Story 3.2 (RS oidc_bearer):** D43 + D62 (PyJWKClient HTTP fetch has no timeout) + D63 (`WWW-Authenticate` header) + D64 (leeway/nbf coverage) + D65 (aud-as-list test gap) + D67 (empty `sub` → 412). D63, D64, D67 are in AC10. D62, D65 are RFC/test-quality nits below the AC10 cut-line but the developer may include them if Task 5.1 confirms they're security-relevant.
- **From Story 3.5 (BFF ResourceServerClient):** D80 (refresh race) + D81 (BFF VALIDATION_ERROR drift) + D82 (per-call AsyncClient) + D83 (`follow_redirects=False`) + D84 (log hygiene). D80, D81, D83, D84 in AC10.
- **From Story 4.2 (BFF estimate proxy):** confirmed BFF→RS path passes only `pages` (no `sub` injection) — Threat 7 (confused-deputy) is pinned by `tests/services/test_resource_server_client.py::test_compute_estimate_*`.

### Git intelligence (recent commits relevant to security surface)

- `3e3612a feat(4.4): E2E specs — J3 estimate + J6 RS unavailable` — baseline; no security surface change.
- `bb15aca Merge story 4.3 — SPA EstimateCell real component + BooksService.requestEstimate` — last SPA source touch; no new security surface.
- `b905307 chore(4.2): code review — P1-P7 applied, mark done, log D119-D126` — last BFF security-surface adjustments (P1 centralized RsUnavailable in `_do_rs_call`).
- `19cb3f8 feat(4.1): RS POST /v1/estimate + estimate_service + format_duration helper` — last RS security-surface addition (`POST /v1/estimate` + scope dep).
- Older security-surface commits (Stories 1.5 / 1.6 / 1.7 / 1.13 / 3.2 / 3.3 / 3.4 / 3.5) are the origin commits for the controls this story documents. The document does not cite git SHAs (paths + line numbers are the citation form); the SHA list above is for the dev's mental model.

**Implication:** the BFF / RS / SPA security surface is frozen as of `3e3612a`. No commits between this story's branch and HEAD touch any cited file.

### Testing standards (for this story specifically)

- **No new tests.** This is a pure doc story; the existing test surface (BFF 543 / RS 324 / SPA 152 / E2E 26) already pins every claim the document makes.
- **No coverage delta.** Story 5.1 captured the per-surface aggregates at `3e3612a` (BFF 97.26%, RS 98.33%, SPA 94.71%/91.16%/95.74%/94.52%, E2E 6/26). This story does not regress them.
- **Document-quality checks (Task 7.3):**
  - All Markdown code fences balanced.
  - All `[label](path)` references resolve to existing files in the repo (run `grep -oE '\[\`[^]]+\`\]\([^)]+\)' docs/security-review.md` and spot-check each).
  - Section anchors are present (`## 1. Token...` → `#1-token-and-transport` slug behavior in standard MD renderers).
  - No trailing whitespace; no mixed indent.

### Latest tech information

- **PyJWT** — current stable is `>=2.10`, with `PyJWKClient` shipping the `kid` cache-miss single-re-fetch behavior the architecture relies on. No breaking changes in the JWKS path between the version Story 1.5 / 3.2 pinned and the current. Validate / Verify CVE feed at the date of authoring (no scanner integration required).
- **Authlib** — current stable, sync + async OIDC client. The BFF uses the async branch via httpx integration. No known security CVEs in the version range used.
- **Angular 21** + **Tailwind CSS 4** — current stable. Angular's template-string auto-escape behavior is unchanged from earlier majors (defense in depth against XSS in templates). Tailwind 4's `@theme` block emits inline `<style>` content which is why `style-src 'unsafe-inline'` is in CSP.
- **httpx** — async HTTP client; default `follow_redirects=False` per D83 (AC10 item).
- **FastAPI / SQLModel / Pydantic v2** — archetype-pinned. Pydantic v2 default behavior on validation includes raw input in `ctx` for some error subclasses, hence the allow-list-vs-deny-list discussion in D68 (test-quality, below AC10 cut-line).

### References

- [Source: `_bmad-output/planning-artifacts/PRD.md#9` line 90] (six-topic envelope — load-bearing).
- [Source: `_bmad-output/planning-artifacts/epics.md#Story 5.2` lines 1800–1849] (verbatim AC source).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Authentication & Security` lines 343–354] (A1–A8 decisions).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Architectural Constraints` lines 72–84] (PRD §8 constraints carried through).
- [Source: `_bmad-output/planning-artifacts/architecture.md#API & Communication Patterns` lines 356–416] (C1–C6 — endpoint catalog, scope table, timeouts).
- [Source: `_bmad-output/planning-artifacts/architecture.md#Operational Details` lines 1317–1373] (test-reset gate, token storage at rest, idle/absolute timeout).
- [Source: `services/bff/src/bff/auth/keycloak_cookie_session.py`] (OIDC + PKCE + state-id signer + id-token verify + revoke + end-session).
- [Source: `services/bff/src/bff/auth/csrf.py`] (CSRF middleware — double-submit + Origin/Referer + constant-time compare).
- [Source: `services/bff/src/bff/middleware/security_headers.py`] (CSP middleware — exact bytes at lines 17–21).
- [Source: `services/bff/src/bff/api/auth.py`] (cookie attribute call sites: 119–127, 155–165, 285–301).
- [Source: `services/bff/src/bff/models/entities/session.py`] (session SQLModel with token columns).
- [Source: `services/bff/src/bff/models/entities/auth_state.py`] (auth-state SQLModel with PKCE verifier column).
- [Source: `services/bff/src/bff/services/session_service.py`] (256-bit ID gen + retry-on-IntegrityError).
- [Source: `services/bff/src/bff/services/resource_server_client.py`] (bearer propagation + 401-refresh-replay).
- [Source: `services/bff/src/bff/core/errors.py`] (error envelope codes).
- [Source: `services/resource-server/src/resource_server/auth/oidc_bearer.py`] (`_validate_access_token`, `require_scope` factory).
- [Source: `services/resource-server/src/resource_server/api/reading_speed.py`] (scope deps).
- [Source: `services/resource-server/src/resource_server/api/estimate.py`] (scope dep).
- [Source: `keycloak/realm-bmad-books.json`] (realm + clients + scopes + audience mapper).
- [Source: `spa/src/app/shared/http/csrf-interceptor.ts`] (SPA CSRF echo).
- [Source: `services/bff/tests/auth/test_keycloak_cookie_session.py`] (OIDC + cookie-attribute pins).
- [Source: `services/bff/tests/auth/test_csrf.py`] (CSRF scenarios).
- [Source: `services/bff/tests/middleware/test_security_headers.py`] (CSP byte-for-byte).
- [Source: `services/bff/tests/services/test_session_service.py`] (session CRUD).
- [Source: `services/bff/tests/services/test_resource_server_client.py`] (bearer + 401-replay).
- [Source: `services/resource-server/tests/auth/test_oidc_bearer.py`] (RS JWKS + iss/aud/exp + scope membership).
- [Source: `services/resource-server/tests/api/test_reading_speed.py`] (per-endpoint scope 403).
- [Source: `services/resource-server/tests/api/test_estimate.py`] (per-endpoint scope 403).
- [Source: `_bmad-output/implementation-artifacts/deferred-work.md`] (D-numbers for AC10).
- [Source: `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md`] (precedent doc-only story; README placement convention).
- [Source: `README.md` lines 22–30] (existing "Architecture overview" section — insertion point for AC11 reference).
- [Pattern: `docs/coverage-report.md` reference line (README line 26)] (one-line reference style to mirror).

## Definition of Done

1. `docs/security-review.md` exists with all eleven sections required by AC1 + AC2–AC11 (header, six PRD §9 topic sections, Accepted Risks, Threat Model Summary, Known Gaps / Future Work, and the README is updated).
2. The document's header cites the **commit SHA the run was made against** (`git rev-parse HEAD`) and the **run date** in ISO-8601 form.
3. Each of §1–§6 cites at least one implementing code path (file + line range) and at least one pin-test file. Citations are accurate — files exist, line ranges contain what the document claims.
4. §6 (Standard SPA concerns) quotes the CSP value byte-for-byte from `services/bff/src/bff/middleware/security_headers.py:17–21`.
5. "Accepted Risks" subsection enumerates the three items from AC8 with mitigation + production alternative + architecture-line citation.
6. "Threat Model Summary" enumerates the seven threats from AC9, each with one-sentence statement + one-paragraph mitigation. No tables; prose only.
7. "Known Gaps / Future Work" enumerates the 18 items from AC10 (minimum), each with the defer-ID citation.
8. `README.md` contains one new reference line to `docs/security-review.md`, placed directly after the existing `docs/coverage-report.md` reference (line 26).
9. `git status` shows the diff is exactly: `docs/security-review.md` (new), `README.md` (+1 line), `_bmad-output/implementation-artifacts/5-2-security-review-document.md` (this file, Tasks updated), `_bmad-output/implementation-artifacts/sprint-status.yaml` (status transitions), and optionally `_bmad-output/implementation-artifacts/deferred-work.md` if Task 8.1 surfaced a new defer.
10. No production source under `services/bff/src/**`, `services/resource-server/src/**`, `spa/src/**` is modified. No new or modified test files under `services/*/tests/**`, `spa/src/**/*.spec.ts`, or `e2e/**`. No infra changes under `compose/**`, `docker-compose.yml`, `Justfile`, `keycloak/**`. No planning-artifact changes under `_bmad-output/planning-artifacts/**`.
11. Markdown lint sanity passes (code fences balanced; internal anchor refs render; every `[label](path)` resolves to an existing repo path).
12. `_bmad-output/implementation-artifacts/sprint-status.yaml` reflects `5-2-security-review-document: ready-for-dev → in-progress → review`. `epic-5` remains `in-progress`.
13. Any items surfaced during dev / code review that are not actioned here are logged in `_bmad-output/implementation-artifacts/deferred-work.md` under a new "Deferred from: dev of 5-2-..." section with severity / "Belongs to" tags. Expected count: zero (per the "Scope" rules).

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context).

### Debug Log References

**Worktree setup (pre-dev sync):**
```
$ git rev-parse HEAD
3e3612ac46d852fd14a4d3dbbd453ffd78c3e51b
$ # Worktree was created from origin/main at 3e3612a (default `fresh` baseRef).
$ # Story 5.1's outputs (docs/coverage-report.md + README line 26 + 5-1 story file)
$ # and the latest sprint-status.yaml were synced from the parent repo to put the
$ # worktree in the "5.1=done, 5.2=ready-for-dev" baseline before dev started.
$ cp ../../../_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md _bmad-output/implementation-artifacts/
$ cp ../../../_bmad-output/implementation-artifacts/sprint-status.yaml _bmad-output/implementation-artifacts/
$ cp ../../../_bmad-output/implementation-artifacts/deferred-work.md _bmad-output/implementation-artifacts/
$ cp ../../../README.md .
$ mkdir -p docs && cp ../../../docs/coverage-report.md docs/
```

**Path / line-range verification (Task 1):**
```
$ ls services/bff/src/bff/auth/
__init__.py  csrf.py  keycloak_cookie_session.py  pkce.py
$ ls services/bff/src/bff/middleware/
__init__.py  security_headers.py
$ ls services/bff/src/bff/models/entities/
__init__.py  auth_state.py  book.py  session.py     ← actual canonical path
$ ls services/resource-server/src/resource_server/auth/
__init__.py  contracts.py  dependencies.py  entra.py  factory.py  models.py  none.py  oidc_bearer.py  role_mapping.py
$ ls services/resource-server/src/resource_server/api/
__init__.py  estimate.py  health.py  reading_speed.py  schemas/  test_reset.py  v1/  v2/
$ grep -n "^def test_\|^async def test_" services/resource-server/tests/api/test_reading_speed.py | grep -i scope
76:async def test_get_returns_403_forbidden_scope_when_only_write_scope_present(
136:async def test_put_returns_403_forbidden_scope_when_only_read_scope_present(
$ sed -n '17,21p' services/bff/src/bff/middleware/security_headers.py
_CSP_VALUE: Final[str] = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'"
)   ← CSP value quoted byte-for-byte into the document
```

**Markdown lint sanity (Task 7.3):**
```
$ wc -l docs/security-review.md README.md
     553 docs/security-review.md
      32 README.md
$ grep -cE '^```' docs/security-review.md     # 28 fences → 14 balanced code blocks
$ grep -c "^## " docs/security-review.md       # 9 H2 sections
$ python verify_relative_links.py              # 31 ../paths all resolve
OK — 31 relative links all resolve.
```

**git status (Task 7.1):**
```
$ git status --short
 M README.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
?? _bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md
?? _bmad-output/implementation-artifacts/5-2-security-review-document.md
?? docs/
$ git diff --stat
 README.md                                                | 4 ++++
 _bmad-output/implementation-artifacts/sprint-status.yaml | 8 ++++----
 2 files changed, 8 insertions(+), 4 deletions(-)
```

Doc-only diff confirmed — no production source, tests, compose, Justfile, keycloak, or planning-artifact files modified.

### Completion Notes List

- **Pure-documentation deliverable as scoped.** The new `docs/security-review.md` (553 lines, 14 code blocks, 31 internal links) is the entirety of the production-facing diff alongside the +4-line README modification (one new reference line + a blank line). No production source / tests / config / infra files were touched. Failure-prevention checklist items #1 ("do not fix a defer") and #14 (do not modify Story 5.1's README line) were observed strictly — the new README line was appended after the coverage-report line, not in place of or interleaved with it.
- **Worktree pre-sync rationale.** This worktree was created via `EnterWorktree` with the default `fresh` baseRef, branching from `origin/main` at `3e3612a`. The parent repo's working tree had Story 5.1's deliverables (`docs/coverage-report.md` + README line 26 + the 5-1 story file) and the latest sprint-status.yaml uncommitted. Six prerequisite files were copied into the worktree at dev-start so that AC11's "place the reference line directly after the existing coverage-report.md reference" rule had a real anchor to mirror. The sync was logged in the Debug Log References section above; the synced files are part of the visible `git status --short` output.
- **One path correction applied to the document inline.** The epic AC at line 1812 cited `services/bff/src/bff/db/models/session.py`. The actual archetype-conformant path is `services/bff/src/bff/models/entities/session.py`. The story file already flagged this as a known stale source-hint; the document cites the actual canonical path with a parenthetical note ("the epic AC's `db/models/...` form is a stale source-hint; this is the same file") so a reviewer reading the document can trace it without confusion.
- **Three accepted-risks subsection: AR1 / AR2 / AR3.** AR1 (plaintext token storage in SQLite) is the document's primary accepted-risk anchor — it cites architecture lines 1362–1368 verbatim and offers three production-deployment alternatives (KEK column encryption, dedicated encrypted store, JWE-encrypted session cookie). AR2 (plaintext PKCE `code_verifier`) is the secondary risk under the same envelope, citing defer D42's "low" severity ratification. AR3 (no idle timeout) explicitly enumerates the production-hardening alternative (explicit `last_activity_at` column + tighter absolute timeout).
- **Seven-threat model authored in prose form per AC9.** Each threat is one sentence + one short paragraph (2–4 sentences) mitigation. No STRIDE / LINDDUN matrix; no attack-tree diagrams. T4 (direct RS access) is explicitly flagged as INTENTIONALLY ACCEPTED — this is the OAuth contract, not a defect. T7 (confused-deputy via `sub` injection) is pinned by two architectural rules (BFF never injects `sub`; RS reads `sub` only from JWT) and the test files that pin each rule are cited inline.
- **Known Gaps subsection covers 19 items (exceeding the AC10 minimum of 18).** Items: CSP hardening (D371), additional HTTP security headers (D372), PyJWT `leeway=0` (D43+D64), missing `WWW-Authenticate: Bearer` (D63), empty-`sub` → 412 (D67), refresh-rotation race (D80), httpx defaults `follow_redirects=False` + per-call clients (D82+D83), log hygiene + `sub` cleartext (D84), Bearer header parsing (D73+D74+D85), BFF `change-me` placeholder parity (D71), `router` exposed via `__all__` (D75), non-`AppException` envelope (D79), BFF `VALIDATION_ERROR` drift (D81), health endpoint amplification (D25), `BFF_CLIENT_SECRET` shared with Playwright runner (D440), log-injection on `sub` (D441), `session_not_found` envelope shape divergence (D442), zero-width whitespace input (D470), and the no-CI-workflow scope decision. Story 5.2 names these and explicitly does NOT close them.
- **Failure-prevention checklist verified:** items 1 (no defer fix), 2 (no casual new defers — zero logged), 3 (path-shift correction applied), 4 (CSP quoted byte-for-byte from `security_headers.py:17–21`), 5 (severity preserved verbatim from `deferred-work.md`), 6 (no OWASP / STRIDE cross-walk), 7 (no scanner output), 8 (no README rewrite — single line), 9 (no TODO placeholders), 10 (7 threats minimum met), 11 (no secrets cited — only env var names), 12 (no PKCE verifier value cited), 13 (Accepted-Risks vs Known-Gaps distinction respected), 14 (Story 5.1's README line unchanged).
- **One Python 3.14 language-version observation, not actioned.** `services/bff/src/bff/auth/csrf.py:103` carries the syntax `except ValueError, TypeError:`. Python 3.14 parses and runs this — the catch covers both exception types correctly. In earlier Python 3.x versions this would be a `SyntaxError`. The BFF test suite passes (543/543 green per Story 5.1's coverage run), so behavior is correct. This is not a security defect, is not in scope for Story 5.2's diff, and is not logged as a defer — it is a minor language-version readability item that a future refactor pass could clean up by switching to the canonical `except (ValueError, TypeError):` tuple form.

### File List

**Created (Task 2 + 3 + 4 + 5):**
- `docs/security-review.md` — the security review document (553 lines).

**Modified (Task 6):**
- `README.md` — single new reference line under "Architecture overview", placed directly after the existing `docs/coverage-report.md` reference (+2 lines: the new ref line + a blank separator).

**Modified (workflow-managed):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `5-2-security-review-document` status transitioned `ready-for-dev` → `in-progress` → `review`; `epic-5` stays `in-progress`; `last_updated` extended with dev-pass narrative.
- `_bmad-output/implementation-artifacts/5-2-security-review-document.md` (this file) — Tasks/Subtasks checkboxes marked; Dev Agent Record filled; File List populated; Change Log v1.0 entry added; Status `ready-for-dev` → `review`.

**Synced at worktree setup (Debug Log above; not part of the story's net diff):**
- `_bmad-output/implementation-artifacts/5-1-coverage-audit-gap-fill.md` — copied from parent (Story 5.1's deliverable).
- `_bmad-output/implementation-artifacts/deferred-work.md` — copied from parent (latest as of `3e3612a` + downstream patches).
- `docs/coverage-report.md` — copied from parent (Story 5.1's deliverable; the README line 26 anchor for AC11 mirrors it).

**Explicitly NOT modified** (verified via `git diff --stat` and `git status --short`): `services/bff/src/**`, `services/bff/tests/**`, `services/bff/pyproject.toml`, `services/resource-server/src/**`, `services/resource-server/tests/**`, `services/resource-server/pyproject.toml`, `spa/src/**`, `spa/package.json`, `spa/angular.json`, `e2e/**`, `compose/**`, `docker-compose.yml`, `Justfile`, `keycloak/**`, `_bmad/**`, `_bmad-output/planning-artifacts/**`.

### Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-05-18 | 0.1 | Story file created. Baseline commit `3e3612a` (Story 4.4 merge to `main`; Story 5.1 in review). Epic 5 = in-progress (transitioned by 5.1). All Epic 1–4 prerequisites done. Doc-only deliverable: one new file (`docs/security-review.md`) + one README reference line. Six PRD §9 topics (token storage/transport, cookie attrs, CSRF, JWT validation, scope enforcement, SPA concerns) each citing implementing code path + pin-test. Three accepted-risks (token plaintext at rest, PKCE verifier plaintext, no idle timeout). Seven-threat model (XSS / CSRF / replay / direct RS / scope escalation / replay-after-logout / confused-deputy). 18-item Known Gaps subsection consolidating existing defers (D25, D42, D43, D63, D64, D67, D71, D73, D74, D75, D79, D80, D81, D83, D84, D85, D369, D371, D372, D440, D441, D442, D470 + the CSP hardening + extra headers items + no GitHub Actions CI). Story 5.2 explicitly does NOT close any of these — they remain deferred. README reference mirrors Story 5.1's placement at line 26. | claude-opus-4-7 |
| 2026-05-18 | 1.0 | Dev pass complete; status `ready-for-dev` → `review`. Worktree `E5S2` synced from parent at dev-start (5.1 was already done on parent; 5.1 outputs + sprint-status.yaml + deferred-work.md + README's line-26 anchor copied in so AC11 had a real placement target). Authored `docs/security-review.md` (553 lines): header with `2026-05-18` run date + `3e3612a` baseline SHA; six PRD §9 topic sections each with implementing code-path + pin-test citations (CSP value quoted byte-for-byte from `security_headers.py:17–21`); three Accepted Risks (AR1 plaintext token storage at `:1362–1368`, AR2 plaintext PKCE `code_verifier` per D42, AR3 no idle timeout at `:1369–1373`); seven-threat model in prose (T1 XSS through T7 confused-deputy); 19-item Known Gaps subsection covering D371 + D372 + D43+D64 + D63 + D67 + D80 + D82+D83 + D84 + D73+D74+D85 + D71 + D75 + D79 + D81 + D25 + D440 + D441 + D442 + D470 + no-CI item (one over the AC10 minimum of 18). Added single README reference line directly after Story 5.1's `docs/coverage-report.md` line (README: 31 → 33 lines). One path correction applied inline: epic AC's `services/bff/src/bff/db/models/session.py` corrected to canonical `services/bff/src/bff/models/entities/session.py`. Zero production code / test / infra changes — `git diff --stat` shows only `README.md` (+4) and `sprint-status.yaml` (+8/-4); `docs/security-review.md` is new in `?? docs/`. Markdown lint sanity: 28 code fences = 14 balanced blocks; 9 H2 sections matching the AC1 structure; all 31 relative `../*` links resolve to existing repo files. No new defers logged (Task 8.1 confirms — one Python 3.14 language-version observation on `csrf.py:103` was noted but is not security-relevant and not in scope to fix here). Failure-prevention checklist items 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 all observed. | claude-opus-4-7 |
