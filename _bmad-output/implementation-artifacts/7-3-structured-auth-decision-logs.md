# Story 7.3: Structured auth-decision logs (ACME schema verbatim)

Status: backlog

## Story

As an operator reading the POC's logs,
I want every authorization decision (allow, deny, login success, login failure, token exchange, refresh) to emit a structured log entry with the exact `{timestamp, sub, decision, reason}` schema specified in the ACME-TS design principles,
so that auth-related operational queries can be answered by a single grep against the structured-logging surface (PRD §12 — structured logging is the only operational-visibility surface in this POC).

## Acceptance Criteria

**AC1 — Schema and helper.** New module `services/bff/src/bff/aop/auth_logging.py` (mirror on the RS) exposes:
```python
class AuthDecision(StrEnum):
    ALLOW           = "allow"
    DENY            = "deny"
    LOGIN_SUCCESS   = "login_success"
    LOGIN_FAILURE   = "login_failure"
    TOKEN_EXCHANGE  = "token_exchange"
    REFRESH         = "refresh"

def emit_auth_decision(
    *,
    decision: AuthDecision,
    reason: str,            # short classifier; MUST NOT contain token material
    sub: str | None = None,
) -> None:
    """Emit a structured auth-decision log entry. Schema is exactly
    `{timestamp, sub, decision, reason}` per ACME-TS design principle P8.
    `timestamp` is UTC ISO-8601 with `Z`. `sub` may be None (e.g., pre-callback).
    The archetype's JSON formatter inflates the entry to a full structured line."""
```

The helper logs at level `INFO` (allow / login_success / token_exchange / refresh) or `WARNING` (deny / login_failure). It is the **only** code path that emits these events — no scattered `logger.info("auth_X")` calls.

**AC2 — Call sites converted.** Every existing site that already emits an `auth_*` log message in BFF or RS is converted to use `emit_auth_decision(...)`. Concretely on the BFF:
- `services/bff/src/bff/api/auth.py:167-172` (auth_state_created)  → `emit_auth_decision(decision=LOGIN_SUCCESS, reason="auth_state_created", sub=None)`. *Wait — LOGIN_SUCCESS fires at session creation, not state creation. Use a new reason string and skip the decision until the row binds to a sub.*
- `services/bff/src/bff/api/auth.py:188-272` (each `_auth_state_invalid_response` warning path) → `LOGIN_FAILURE` with the specific reason classifier (`missing_state`, `state_cookie_invalid`, `state_row_missing_or_expired`, `cookie_row_id_mismatch`, `missing_code`, `token_exchange_failed`, `id_token_invalid`, `id_token_missing`, `exp_invalid`).
- `services/bff/src/bff/api/auth.py:315-321` (auth_callback_success) → `LOGIN_SUCCESS` with reason `"session_created"`, sub from claims.
- `services/bff/src/bff/api/auth.py:429-505` (logout flow) → `ALLOW` with reason `"logout"`; failures of revocation/end_session log separately at `DENY` with reason `"revocation_failed"` / `"end_session_failed"`.
- BFF→Keycloak `_refresh_access_token` (the existing `resource_server_client.py`) → `REFRESH` on success, `DENY` reason=`"refresh_failed"` on failure.

On the RS:
- `oidc_bearer.py` validation entry → `ALLOW` (reason=`"jwt_valid"`) on success.
- `oidc_bearer.py` rejection paths → `DENY` with specific reasons (`token_missing`, `signature_invalid`, `audience_mismatch`, `issuer_mismatch`, `exp_past`, `scope_insufficient`).

**AC3 — `sub` never logs untruncated.** `emit_auth_decision` truncates `sub` to first 8 chars + `…` if longer than 12 chars, matching the existing `_safe_session_id_log` convention in `services/bff/src/bff/api/auth.py`. No PII (preferred_username, email) ever enters the schema.

**AC4 — No token material in `reason`.** Static analysis test: a pytest fixture intercepts every `emit_auth_decision` call during the test suite and asserts the `reason` string does not contain any of: `access_token`, `refresh_token`, `id_token`, `Bearer `, a JWT-shaped substring (regex `[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`), or a base64url string longer than 32 chars.

**AC5 — JSON output verified.** When `LOG_MODE=json` (archetype default in prod), each emitted line is valid JSON with at minimum the keys `timestamp`, `sub`, `decision`, `reason`, `level`, `logger`. A pin-test captures one of each `AuthDecision` value and asserts the JSON shape.

**AC6 — Migration guide.** `docs/security-review.md` gets a new subsection "§7 Auth-decision audit trail" describing the schema, listing the six `AuthDecision` values + their reason vocabularies, and pointing at the source modules. README's "Architecture overview" gets one line.

## Dependencies

- Closes principle gap **P8** (observability — structured decision logs) from sprint-change-proposal-2026-05-21.md.
- Touches: new `auth_logging.py` module (BFF + RS), every existing `logger.info("auth_*"` / `logger.warning("auth_*"` call site, multiple test files, `docs/security-review.md`, README.
- Does NOT change the archetype's JSON logging config — the new helper rides on top of the existing structured-logging surface.

## Notes

- The archetype's `log_io` AOP decorator continues to emit per-method I/O at DEBUG; this story is **additive** — auth decisions emit on top of `log_io`, not in place of it.
- This is the first story in the POC to formalize an authorization-event schema. If the ACME real-project later adds fields (`request_id`, `scope`, `client_id`), they can be added as optional kwargs to `emit_auth_decision` without breaking the ACME-minimum 4-field guarantee.
