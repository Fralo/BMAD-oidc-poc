# Story 7.2: OIDC discovery bootstrap (no more hardcoded endpoint URLs)

Status: backlog

## Story

As a developer promoting the POC between environments,
I want the BFF and Resource Server to read all OIDC endpoint URLs from `${OIDC_ISSUER_URL}/.well-known/openid-configuration` at startup,
so that environment promotion requires changing only the ISSUER base URL — matching the ACME-TS "discovery over hardcoding" principle.

## Acceptance Criteria

**AC1 — Single env var per service.** After this story, BFF requires only `OIDC_ISSUER_URL` and `OIDC_CLIENT_ID` (+ `BFF_CLIENT_SECRET`). RS requires only `OIDC_ISSUER_URL` and `OIDC_AUDIENCE`. The previously-required `OIDC_JWKS_URL`, `OIDC_AUTHORIZE_URL_BROWSER`, and any token/end-session/revocation URLs are no longer accepted from env (consumers raise on use of removed settings; deprecation grace period is **not** required — this is a POC).

**AC2 — Discovery happens at startup.** On BFF startup (FastAPI `lifespan` startup hook), the service GETs `${OIDC_ISSUER_URL}/.well-known/openid-configuration` once, parses the response, and stashes the resolved URLs (`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `end_session_endpoint`, `revocation_endpoint`, `issuer`) into an `OidcDiscovery` dataclass exposed as a FastAPI dependency. Same pattern on the Resource Server for `jwks_uri` and `issuer`.

**AC3 — Fail-fast on unreachable AS.** If discovery fails (connection error, non-2xx, malformed JSON, missing required field), the service refuses to start (`uvicorn` exits non-zero with a clear log line). No silent fallback. The `/health` probe already tracks discovery reachability for runtime — startup gating is a separate, stricter check.

**AC4 — Browser-facing authorize URL split preserved.** Discovery returns the back-channel issuer; the BFF still needs a browser-facing authorize URL for the `/auth/login` 302 (compose-internal vs browser-resolvable hostnames — see D2/D8 in deferred-work). The implementation keeps a **derived** browser-facing URL via a new `OIDC_PUBLIC_BASE_URL` env var that defaults to `${OIDC_ISSUER_URL}` and is overridden only in compose dev. The discovery doc's `authorization_endpoint` path suffix is preserved; only the host:port is swapped.

**AC5 — Tests.** Unit tests for the discovery loader covering: happy path; connection refused → boot fails; 404 → boot fails; 200 with missing `jwks_uri` → boot fails; 200 with extra unknown fields → boot succeeds, unknown fields ignored. Integration tests verify `/auth/login`, `/auth/callback`, and `/auth/logout` all use the discovered URLs (no string-concat from `OIDC_ISSUER_URL`). The synthetic IdP fixture exposes `discovery_doc` already — no harness changes needed.

**AC6 — Config + docs cleanup.** `.env.example` updated: removes `OIDC_JWKS_URL`, `OIDC_AUTHORIZE_URL_BROWSER`; documents `OIDC_PUBLIC_BASE_URL` with its compose-default. `services/bff/src/bff/core/config.py` and `services/resource-server/src/resource_server/core/config.py` drop the removed fields and their validators. README + `docs/security-review.md` updated to reflect the simpler env contract.

## Dependencies

- Closes principle gap **P6** (discovery over hardcoding) from sprint-change-proposal-2026-05-21.md.
- Touches: BFF + RS config modules, BFF + RS startup hooks, BFF auth module (URL resolution), `.env.example`, README, security-review.md, multiple BFF + RS test files.
- Story 7.2 should land **after** Story 7.3 if you want auth-decision logs to also report the discovery fetch as a structured event.

## Notes

- The BFF currently fetches the discovery doc as a `/health` reachability probe (`services/bff/src/bff/api/health.py:97`). This story repurposes that probe into a **startup gate** + caches the parsed doc for the rest of the process lifetime.
- The RS currently uses `OIDC_JWKS_URL` directly with PyJWT's `PyJWKClient`. This story switches it to read `jwks_uri` from the discovery doc — same client, derived URL.
- No PKCE-era code-paths to remove here (that was Group E of the 2026-05-21 sprint change).
