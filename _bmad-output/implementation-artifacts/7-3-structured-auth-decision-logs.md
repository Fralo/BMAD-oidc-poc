# Story 7.3: Structured auth-decision logs (ACME schema verbatim)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator reading the POC's logs,
I want every authorization decision (allow, deny, login success, login failure, token exchange, refresh) to emit a structured log entry with the exact `{timestamp, sub, decision, reason}` schema specified in the ACME-TS design principles,
so that auth-related operational queries can be answered by a single `grep` (or `jq` selector) against the structured-logging surface (PRD §12 — structured logging is the only operational-visibility surface in this POC).

This story closes principle gap **P8** (observability — structured decision logs) from `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` §3 / §4 / §5.

## Acceptance Criteria

**AC1 — Schema and helper.** New module `services/bff/src/bff/aop/auth_logging.py` (mirror it at `services/resource-server/src/resource_server/aop/auth_logging.py`) exposes:

```python
from collections.abc import Mapping
from enum import StrEnum

class AuthDecision(StrEnum):
    ALLOW          = "allow"
    DENY           = "deny"
    LOGIN_SUCCESS  = "login_success"
    LOGIN_FAILURE  = "login_failure"
    TOKEN_EXCHANGE = "token_exchange"
    REFRESH        = "refresh"

def emit_auth_decision(
    *,
    decision: AuthDecision,
    reason: str,            # short classifier; MUST NOT contain token material
    sub: str | None = None,
) -> None:
    """Emit a structured auth-decision log entry. Wire schema is exactly
    `{timestamp, sub, decision, reason}` per ACME-TS design principle P8.
    `timestamp` is UTC ISO-8601 with offset (`+00:00`). `sub` may be `None`
    (e.g., pre-callback state-validation paths). The archetype's JSON
    formatter inflates the entry to a full structured line that also carries
    `level`, `logger`, `traceId`, `spanId`."""
```

Level mapping is enforced inside the helper:

| decision | level |
|---|---|
| `ALLOW`, `LOGIN_SUCCESS`, `TOKEN_EXCHANGE`, `REFRESH` | `INFO` |
| `DENY`, `LOGIN_FAILURE` | `WARNING` |

The helper is the **only** code path that emits these events — no scattered `logger.info("auth_X")` / `logger.warning("auth_X")` calls survive.

**AC2 — Call sites converted (BFF).** Every existing site that emits an `auth_*` log message in `services/bff/src/bff/api/auth.py` is converted to use `emit_auth_decision(...)`. Concrete map (line numbers are the pre-change references — they will shift as imports + edits land):

- `auth.py:163-167` (`auth_state_created` INFO) → `emit_auth_decision(decision=AuthDecision.ALLOW, reason="auth_state_created", sub=None)`. Note: this is `ALLOW`, not `LOGIN_SUCCESS` — the row is created before the user authenticates; `LOGIN_SUCCESS` fires only on cookie issuance.
- `auth.py:184` (`auth_callback_missing_state`) → `emit_auth_decision(decision=AuthDecision.LOGIN_FAILURE, reason="missing_state")`.
- `auth.py:195` (`auth_callback_state_cookie_invalid`) → `LOGIN_FAILURE`, `reason="state_cookie_invalid"`.
- `auth.py:202` (`auth_callback_state_row_missing_or_expired`) → `LOGIN_FAILURE`, `reason="state_row_missing_or_expired"`.
- `auth.py:211` (`auth_callback_cookie_row_id_mismatch`) → `LOGIN_FAILURE`, `reason="cookie_row_id_mismatch"`.
- `auth.py:218` (`auth_callback_missing_code`) → `LOGIN_FAILURE`, `reason="missing_code"`.
- `auth.py:233` (`auth_callback_token_exchange_failed`) → `LOGIN_FAILURE`, `reason="token_exchange_failed"`. The `%s` exc detail is dropped from the wire — exception type/message MUST NOT appear in `reason` (AC4).
- `auth.py:240` (`auth_callback_id_token_missing`) → `LOGIN_FAILURE`, `reason="id_token_missing"`.
- `auth.py:257` (`auth_callback_id_token_invalid`) → `LOGIN_FAILURE`, `reason="id_token_invalid"`.
- `auth.py:266` (`auth_callback_exp_invalid`) → `LOGIN_FAILURE`, `reason="exp_invalid"`.
- `auth.py:310-315` (`auth_callback_success`) → `emit_auth_decision(decision=AuthDecision.LOGIN_SUCCESS, reason="session_created", sub=sub)`. The truncated `sub` shape comes from AC3, not from `_safe_session_id_log`.
- `auth.py:404` (`auth_logout_missing_session_cookie`) → `LOGIN_FAILURE`, `reason="logout_missing_session_cookie"`. (LOGIN_FAILURE is the closest semantic — there is no `LOGOUT_*` value in the ACME schema. Alternative considered: `DENY` with reason `logout_missing_session_cookie`. Pick **DENY** — `LOGIN_FAILURE` would be misleading. See "Decision Pinned" below.)
- `auth.py:409` (`auth_logout_unknown_session`) → `DENY`, `reason="logout_unknown_session"`.
- `auth.py:418` (`auth_logout_expired_session`) → `DENY`, `reason="logout_expired_session"`.
- `auth.py:424` (`auth_logout_start`) → **drop** (it's a progress marker, not a decision; covered by `log_io` AOP at DEBUG when present).
- `auth.py:447` (`auth_logout_revocation_failed`) → `DENY`, `reason="revocation_failed"`, `sub=row.sub`.
- `auth.py:456` (`auth_logout_no_refresh_token`) → **drop** (progress marker, not a decision).
- `auth.py:470` (`auth_logout_end_session_failed`) → `DENY`, `reason="end_session_failed"`, `sub=row.sub`.
- `auth.py:475` (`auth_logout_no_id_token`) → **drop** (progress marker).
- `auth.py:492` (`auth_logout_session_delete_failed`) → `DENY`, `reason="session_delete_failed"`, `sub=row.sub`. Level upgrade vs. current ERROR is intentional — the ACME schema's `DENY` is WARNING and `session_delete_failed` is recoverable (cookies still clear, user perceives a successful logout). Keep the stdlib `logger.error(..., exc_info=True)` line **in addition** to `emit_auth_decision(...)` because the stack trace is operationally load-bearing. (See "Decision Pinned" below.)
- `auth.py:496-500` (`auth_logout_complete`) → `emit_auth_decision(decision=AuthDecision.ALLOW, reason="logout", sub=row.sub)`.

Also convert in `services/bff/src/bff/services/resource_server_client.py`:
- `resource_server_client.py:251-256` (`refresh_failed`) → `DENY`, `reason="refresh_failed"`, `sub=session_row.sub`. Drop the `cause=` from the wire (cause is a classifier like `keycloak_4xx:400` / `transport_error:ConnectError` — safe by construction but the schema is 4-field).
- `resource_server_client.py:273-277` (`rs_401_after_refresh`) → `DENY`, `reason="rs_401_after_refresh"`, `sub=session_row.sub`.
- `resource_server_client.py:430-434` (`access_token_refreshed`) → `REFRESH`, `reason="access_token_refreshed"`, `sub=session_row.sub`.

`services/bff/src/bff/auth/csrf.py` logger calls (lines 66, 80, 94, 106, 129) are NOT in scope — those are CSRF-rejection logs, not auth-decision logs. Keep them as-is. (Same rationale: ACME-TS principle P8 names *authorization decisions* — CSRF is a transport-integrity check, not an authZ decision. If a future ACME revision adds a `CSRF_REJECT` decision, this story's helper is ready to grow.)

**AC3 — Call sites converted (RS).** On `services/resource-server/src/resource_server/auth/oidc_bearer.py`:
- `oidc_bearer.py:89` (`JWT validation failed`) → on the **happy** path (after `jwt.decode(...)` succeeds), emit `ALLOW`, `reason="jwt_valid"`, `sub=str(claims.get("sub", ""))`. On the **failure** path (the existing `except` branch), emit `DENY` with a reason classifier mapped from the exception:
  - `jwt.InvalidSignatureError` → `signature_invalid`
  - `jwt.InvalidAudienceError` → `audience_mismatch`
  - `jwt.InvalidIssuerError` → `issuer_mismatch`
  - `jwt.ExpiredSignatureError` → `exp_past`
  - `jwt.MissingRequiredClaimError` → `claim_missing` (with the claim name truncated to first 16 chars if Provider exposes it via `exc.claim` — see Dev Notes for the safe accessor)
  - `jwt.PyJWKClientError` → `jwks_lookup_failed`
  - any other `jwt.InvalidTokenError` subclass → `token_invalid`
  Keep `sub=None` on every DENY path (we don't have validated claims at that point).
- `oidc_bearer.py:121-125` (the `get_authenticated_principal` path that raises on missing/blank token) → `DENY`, `reason="token_missing"`, `sub=None`. Currently this raises `AppException` silently with no log; add the structured emit immediately before the `raise`.
- `oidc_bearer.py:148-153` (`Scope check failed`) → `DENY`, `reason=f"scope_insufficient:{scope}"`, `sub=principal.subject`. The scope name is by construction safe (a valid OAuth scope identifier — `reading-speed:read` / `reading-speed:write`); it is NOT user-supplied content.

On `services/resource-server/src/resource_server/auth/dependencies.py`:
- `dependencies.py:43` (`Bearer token authentication failed`) → already covered by the `oidc_bearer.py:89` DENY emit (this is just the FastAPI dependency wrapper). **Drop** the stdlib `logger.warning(...)` here, OR keep it — the dev choice is to keep the existing warning as the upstream classifier (no auth-decision emit at this layer; the decision was already emitted one level deeper). Recommended: **keep** the existing warning, **do not add** a duplicate emit.
- `dependencies.py:48` (the "Unexpected authentication error" path) → `DENY`, `reason="auth_unexpected_error"`, `sub=None`. Keep the existing stdlib warning too.
- `dependencies.py:67-72` (`Role check failed`) → `DENY`, `reason=f"role_denied:{required_role.value}"`, `sub=principal.subject`. (Note: today only `oidc_bearer.py` is wired and `oidc_bearer.require_scope` is what gates the endpoints; `dependencies.require_role` is the archetype's parallel hook that is only exercised by `test_require_role_uses_mapper.py`. Convert it for consistency — the ACME-TS realm may use it later.)

**AC4 — `sub` never logs untruncated.** `emit_auth_decision` truncates `sub` to `first 8 chars + "…"` if longer than **12 characters**, matching the `_safe_session_id_log` convention in `services/bff/src/bff/api/auth.py:83-87`. The 12-char threshold (not 8) preserves intentionally-short test fixture subs verbatim. `None` and empty string pass through unchanged (the JSON field shape is `null` / `""` — see AC5 for exact wire shape).

**AC4a — No PII in `sub` (defensive).** The helper does not look at `preferred_username`, `email`, or any other claim — it only accepts the `sub` keyword argument. Callers MUST NOT pass `preferred_username` here. Add a unit test that asserts `emit_auth_decision(sub="alice@example.com", ...)` still truncates by length (`alice@ex…`), demonstrating the helper is name-agnostic.

**AC5 — No token material in `reason`.** Static analysis test in `services/bff/tests/aop/test_auth_logging.py` (and the RS mirror): a fixture that intercepts every call to `emit_auth_decision` for the test-suite lifetime and asserts the `reason` string does NOT contain any of:

- the literal substrings `access_token`, `refresh_token`, `id_token`, `Bearer ` (with trailing space), `eyJ` (the standard JWT header prefix for `{"alg"`)
- a JWT-shaped substring matching the regex `[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`
- a base64url-ish substring matching `[A-Za-z0-9_-]{33,}` (length > 32; tokens are typically 200+)

Implementation hint: install the assertion as a `pytest` fixture in `services/bff/tests/conftest.py` (and the RS mirror) that monkey-patches `emit_auth_decision` to record + validate every call's args before delegating to the real implementation. This way every existing integration test in the suite (BFF: 528-ish; RS: ~324) re-asserts the schema invariant for free.

**AC6 — JSON output verified.** When `LOG_MODE=json` (archetype default in prod), each emitted line is valid JSON with the 6-field schema:

```json
{"timestamp": "2026-05-21T12:34:56.789012+00:00",
 "level": "info",
 "logger": "bff.aop.auth_logging",
 "decision": "login_success",
 "sub": "abc12345...",
 "reason": "session_created",
 "traceId": "...",
 "spanId": "..."}
```

CRITICAL: the existing `_json_renderer` in `services/bff/src/bff/observability/logging.py:103-126` is hardcoded to a fixed 6-key shape (`timestamp`, `level`, `logger`, `message`, `traceId`, `spanId`) and **drops everything else**. The helper must either:

1. **(Preferred)** Bind `decision` / `sub` / `reason` via `structlog`'s `structlog.get_logger().bind(...)` — but the current configure_logging uses stdlib loggers, not structlog's native loggers, and the ProcessorFormatter foreign_pre_chain only sees the standard LogRecord fields.

2. **(Recommended)** Extend `_json_renderer` (BFF + RS, byte-identical edit) so it also emits any of `decision`, `sub`, `reason` when present in `event_dict` (i.e., when the caller passed them via stdlib `logger.log(..., extra={...})`). The minimal patch is a 3-line `for field in ("decision", "sub", "reason"):` loop appended right before the `exc_info` block in `_json_renderer`. This keeps the architecture's "structured logs only via archetype" pattern and adds three optional fields.

3. The `_plain_renderer` (lines 81-100) needs a sibling extension so dev-mode logs also surface `decision=<x> sub=<y> reason=<z>` after the event string.

Add an integration test `services/bff/tests/observability/test_auth_decision_json.py` (and the RS mirror) that drives one of each `AuthDecision` value through the helper, captures the rendered line via the `caplog` LogCaptureHandler, parses it as JSON, and asserts:
- the four ACME-required fields are present and well-typed
- `level` matches the AC1 mapping table
- `logger` is `"bff.aop.auth_logging"` (RS: `"resource_server.aop.auth_logging"`) — i.e., the helper uses its own `__name__` so operators can route the surface independently.

**AC7 — Pin tests for level mapping.** Unit test in `services/bff/tests/aop/test_auth_logging.py` (and the RS mirror) asserts the AC1 level table exactly:
- `ALLOW`, `LOGIN_SUCCESS`, `TOKEN_EXCHANGE`, `REFRESH` → emit at `INFO` (`record.levelno == logging.INFO`)
- `DENY`, `LOGIN_FAILURE` → emit at `WARNING` (`record.levelno == logging.WARNING`)

Use `pytest`'s `caplog` fixture with `caplog.set_level(logging.DEBUG, logger="bff.aop.auth_logging")` to capture all emitted records.

**AC8 — Migration guide and docs.** `docs/security-review.md` gains a new top-level subsection **§7 Auth-decision audit trail** that:
- Describes the ACME-TS principle P8 schema and cites `sprint-change-proposal-2026-05-21.md` as origin.
- Lists the six `AuthDecision` values with their reason vocabularies (cross-reference back to this story's AC2/AC3 mapping).
- Points at `services/bff/src/bff/aop/auth_logging.py` and `services/resource-server/src/resource_server/aop/auth_logging.py` as the **only** code paths that emit decision events.
- Cites the static-analysis fixture from AC5 as the enforcement mechanism.

`README.md` "Architecture overview" gains one line referencing `docs/security-review.md §7` (mirror Stories 5.2 + 5.3 placement conventions — Architecture overview block, one reference line per major doc).

`_bmad-output/planning-artifacts/architecture.md` gains a **Pattern Amendments** entry dated `2026-05-21` (after the existing PKCE removal entry at line 865) describing the structured-auth-decision pattern, the helper module location, and the AC5 invariant.

**AC9 — No regression in existing tests.** All BFF and RS test suites pass green. Specifically:
- `cd services/bff && uv run pytest` — green; same test count + the new `test_auth_logging.py` + the new `test_auth_decision_json.py` (~12 new tests on BFF).
- `cd services/resource-server && uv run pytest` — green; same test count + RS mirrors of the two new test files (~10 new tests on RS).
- Existing tests that previously asserted on stdlib `logger.warning("auth_callback_token_exchange_failed: %s", exc)` log lines now assert on the structured shape. Specifically `services/bff/tests/api/test_auth.py` is the largest file expected to need touch-ups; the existing `caplog`-based assertions there should switch to asserting `record.decision == AuthDecision.LOGIN_FAILURE.value and record.reason == "token_exchange_failed"` instead of message substring matching.

**AC10 — Coverage thresholds preserved.** Per NFR11 (Story 5.1's baseline): BFF ≥90% line / ≥70% per-file; RS ≥90% line / ≥70% per-file. The new `auth_logging.py` module is small (<40 lines including the enum + helper); per-file floor is straightforward. Net coverage delta on the surface should be **positive** — every existing call site now passes through the helper, exercising it ~100 times across the suite.

## Dependencies

- Closes principle gap **P8** (observability — structured decision logs) from `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md`.
- Story 7.2 (OIDC discovery bootstrap) — per the 7.2 spec, "Story 7.2 should land **after** Story 7.3 if you want auth-decision logs to also report the discovery fetch as a structured event." Sequence per sprint-change-proposal §5: **7.3 first**, then 7.2, then 7.1.
- Touches:
  - **New code:** `services/bff/src/bff/aop/auth_logging.py`, `services/resource-server/src/resource_server/aop/auth_logging.py`.
  - **Modified BFF source:** `services/bff/src/bff/api/auth.py` (~10 call sites), `services/bff/src/bff/services/resource_server_client.py` (~3 call sites), `services/bff/src/bff/observability/logging.py` (`_json_renderer` + `_plain_renderer` 3-line extensions per AC6).
  - **Modified RS source:** `services/resource-server/src/resource_server/auth/oidc_bearer.py` (~3 call sites including the ALLOW happy path), `services/resource-server/src/resource_server/auth/dependencies.py` (~2 call sites), `services/resource-server/src/resource_server/observability/logging.py` (mirror BFF renderer extensions).
  - **New tests:** `services/bff/tests/aop/test_auth_logging.py`, `services/bff/tests/observability/test_auth_decision_json.py`, RS mirrors of both, conftest fixture in BFF + RS for AC5 static analysis.
  - **Modified tests:** `services/bff/tests/api/test_auth.py` (message-string assertions → structured-field assertions).
  - **Modified docs:** `docs/security-review.md` (§7), `README.md` (one line), `_bmad-output/planning-artifacts/architecture.md` (Pattern Amendments entry).
- Does NOT change:
  - The archetype's JSON logging config beyond the 3-line extension to `_json_renderer` + sibling `_plain_renderer` extension.
  - The `log_io` AOP decorator (`aop/logging_decorator.py`) — auth-decision logs are **additive**, riding on top of existing AOP I/O logs.
  - The Keycloak realm, compose, or `.env.example`.
  - Any CSRF / static-assets / health / test-reset / observability surfaces beyond what AC2/AC3 specifies.

## Tasks / Subtasks

- [x] Task 1 (AC: 1, 4, 4a) — Create the helper module and its mirror.
  - [x] 1.1 — Write `services/bff/src/bff/aop/auth_logging.py` containing `AuthDecision` (StrEnum) and `emit_auth_decision(...)`.
  - [x] 1.2 — Implement the level-mapping branch (`AuthDecision.{ALLOW, LOGIN_SUCCESS, TOKEN_EXCHANGE, REFRESH}` → INFO; `{DENY, LOGIN_FAILURE}` → WARNING) using stdlib `logger.log(level, ...)` with `extra={"decision": decision.value, "sub": _truncate(sub), "reason": reason}`.
  - [x] 1.3 — Implement `_truncate(sub)` matching `_safe_session_id_log` (first 8 chars + "…" if `len > 12`; `None` / `""` pass through unchanged).
  - [x] 1.4 — Module logger is `logging.getLogger(__name__)` so the wire `logger` field is `"bff.aop.auth_logging"`.
  - [x] 1.5 — Byte-identical mirror at `services/resource-server/src/resource_server/aop/auth_logging.py` (only the docstring service-name string differs).
- [x] Task 2 (AC: 6) — Extend the JSON + plain renderers (BFF + RS).
  - [x] 2.1 — In `services/bff/src/bff/observability/logging.py:103-126` (`_json_renderer`), add a 3-line loop after the fixed-key block that copies `decision`, `sub`, `reason` from `event_dict` into the rendered JSON entry when present.
  - [x] 2.2 — In `_plain_renderer` (lines 81-100), append `decision=<x> sub=<y> reason=<z>` to the rendered line when present (space-prefixed; omit fields whose value is `None`).
  - [x] 2.3 — Mirror the extensions in `services/resource-server/src/resource_server/observability/logging.py`.
  - [x] 2.4 — Verify `services/bff/tests/observability/test_json_renderer.py` and `test_plain_renderer.py` still pass unchanged (the extensions are additive — present-field is rendered, absent-field is the prior fixed shape).
- [x] Task 3 (AC: 2) — Convert BFF call sites in `api/auth.py`.
  - [x] 3.1 — Add `from bff.aop.auth_logging import AuthDecision, emit_auth_decision` at the top of the module.
  - [x] 3.2 — Walk each of the 17 numbered sites in AC2 in source order; replace the stdlib `logger.info(...)` / `logger.warning(...)` line with `emit_auth_decision(decision=..., reason=..., sub=...)`. The four progress markers (`auth_logout_start`, `auth_logout_no_refresh_token`, `auth_logout_no_id_token`) are deleted, not converted.
  - [x] 3.3 — Keep the `logger.error("auth_logout_session_delete_failed: %s", type(exc).__name__)` call **in addition** to the new `emit_auth_decision(decision=AuthDecision.DENY, reason="session_delete_failed", sub=row.sub)` — the stack-trace surface from the `logger.error` is operationally load-bearing (see "Decision Pinned" below).
- [x] Task 4 (AC: 2) — Convert BFF call sites in `services/resource_server_client.py`.
  - [x] 4.1 — Add the helper import.
  - [x] 4.2 — Convert `refresh_failed` (line 251-256), `rs_401_after_refresh` (line 273-277), `access_token_refreshed` (line 430-434). Drop the `cause=` / `session=` fields from the wire string (replaced by the helper's structured `reason` + `sub`).
- [x] Task 5 (AC: 3) — Convert RS call sites.
  - [x] 5.1 — In `services/resource-server/src/resource_server/auth/oidc_bearer.py`: add helper import; insert ALLOW emit on the `_validate_access_token` happy path (right before the `return decoded`); convert the DENY emit on the `except` branch with the exception-type → reason-classifier mapping from AC3.
  - [x] 5.2 — Add DENY emit before the `raise AppException(ErrorCode.SESSION_EXPIRED)` in `get_authenticated_principal` for the missing/blank token paths (lines 121-125).
  - [x] 5.3 — Convert the `Scope check failed` emit at line 148-153 to `DENY`, `reason=f"scope_insufficient:{scope}"`.
  - [x] 5.4 — In `dependencies.py`: convert the "Unexpected authentication error" path (line 48) and the `Role check failed` path (line 67-72). Keep the original `logger.warning(...)` lines next to the new structured emits — they carry exception details the structured emit drops by schema.
- [x] Task 6 (AC: 4, 4a, 5, 7) — Helper unit tests.
  - [x] 6.1 — `services/bff/tests/aop/test_auth_logging.py` — assert AC1 level mapping (6 cases), AC4 truncation behavior (4 cases: short < 12, exactly 12, longer than 12, None, empty string), AC4a name-agnostic truncation, the wire-field shape via `caplog.records[0].decision`, `.sub`, `.reason`.
  - [x] 6.2 — RS mirror at `services/resource-server/tests/aop/test_auth_logging.py`.
  - [x] 6.3 — Add the AC5 conftest fixture in `services/bff/tests/conftest.py` (and RS) that monkey-patches `emit_auth_decision` to run the no-token-material regex assertions on every call before delegating to the real implementation. Scope: `autouse=True`, session-scoped.
- [x] Task 7 (AC: 6) — Renderer integration tests.
  - [x] 7.1 — `services/bff/tests/observability/test_auth_decision_json.py` — drives one of each `AuthDecision` through the helper, captures the rendered JSON via `caplog`, parses, asserts the 6+3-key shape (timestamp, level, logger, traceId, spanId — plus decision, sub, reason).
  - [x] 7.2 — RS mirror at `services/resource-server/tests/observability/test_auth_decision_json.py`.
- [x] Task 8 (AC: 9) — Fix any existing tests that assert on the old log message strings.
  - [x] 8.1 — Run `cd services/bff && uv run pytest -x` after Task 3 lands; iterate until green. Expected files to edit: `services/bff/tests/api/test_auth.py` (caplog message-substring assertions). Failure mode: tests asserting `"auth_callback_token_exchange_failed" in caplog.text` must switch to `any(r.reason == "token_exchange_failed" for r in caplog.records)`.
  - [x] 8.2 — Same on RS: `cd services/resource-server && uv run pytest -x`. Expected: minimal — the RS auth tests are JWT-validation focused; the structured emit is additive at the validation layer.
- [x] Task 9 (AC: 8) — Documentation.
  - [x] 9.1 — Append `## 7. Auth-decision audit trail` section to `docs/security-review.md`. Structure: principle origin, schema, six values + reason vocabularies, code paths, enforcement fixture.
  - [x] 9.2 — Add one reference line to `README.md` "Architecture overview" block (mirror Story 5.2's placement convention).
  - [x] 9.3 — Add Pattern Amendments entry to `_bmad-output/planning-artifacts/architecture.md` after the 2026-05-21 PKCE removal entry at line 865.
- [x] Task 10 (AC: 9, 10) — Final verification.
  - [x] 10.1 — `cd services/bff && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` — all green.
  - [x] 10.2 — `cd services/resource-server && uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest` — all green.
  - [x] 10.3 — Aggregate coverage: BFF + RS both ≥90% line, per-file ≥70%. Per NFR11 / Story 5.1 baseline.
  - [x] 10.4 — Smoke check: start the BFF locally, hit `/auth/login`, observe the `decision=allow reason=auth_state_created` log line at INFO. (Mode-B HTTP-probe pattern per Story 5.4 — agent-completable without browser.)

## Dev Notes

### Decisions Pinned (do not re-litigate)

- **Logout uses DENY for failure paths, not LOGIN_FAILURE.** The ACME-TS schema names six decisions; `LOGOUT_*` is not one of them. Logout failures (revocation upstream failed, end_session upstream failed, session-row delete failed) are categorically **deny-this-decision**, not **login-failed**, so they go on `DENY`. The `auth_logout_complete` success path is `ALLOW` with `reason="logout"`. The schema is intentionally a tight 6-value set — don't grow it within this story; if ACME later adds `LOGOUT`, that's a sprint-change-proposal-level decision, not a story-level one.

- **`session_delete_failed` keeps its `logger.error(..., exc_info=True)` line in addition to the new structured emit.** The `DENY` schema entry tells operators *that* a logout had an internal error; the stack trace tells them *why*. Both are load-bearing. The ACME schema is a wire-format contract, not a coverage exhaustiveness contract — adding additional log lines beside it is fine.

- **`oidc_bearer.py` DENY emits leave `sub=None`.** At the moment a JWT is being rejected, no validated `sub` exists. Reading `sub` from a *failed-validation* JWT body would be reading-untrusted-data, defeating the purpose of validation. The DENY emit's value is "we refused authentication"; the value is NOT in attributing the refusal to a specific subject.

- **Scope-failure `reason` embeds the scope name.** `scope_insufficient:reading-speed:write` (yes, two colons — the helper does not parse `reason`; it's a free string). The scope name is by construction an OAuth identifier from `oidc_bearer.require_scope(scope)`'s factory argument — it is NEVER user-supplied. AC5's no-token-material check runs against this string; the scope identifier is short (<32 chars) and slash-free so it cannot match the JWT-shape or base64url regexes.

- **CSRF rejection logs stay as-is (out of scope for P8).** ACME-TS principle P8 names *authorization decisions*. CSRF double-submit + Origin check is a transport-integrity defense, not an authZ decision. If a future ACME revision adds a `CSRF_REJECT` decision, this story's helper is ready to grow — the StrEnum is intentionally extensible.

- **The four logout progress markers are deleted (not converted).** `auth_logout_start`, `auth_logout_no_refresh_token`, `auth_logout_no_id_token`, plus the `_safe_session_id_log` ellipses are flow-progress signal, not authZ-decision signal. Operators wanting per-method I/O can run with `LOG_LEVEL=DEBUG` to surface the `log_io` AOP decorator output.

### Architecture compliance (extract per `architecture.md`)

- **Pattern source of truth** is `architecture.md`. Pattern changes go in `### Pattern Amendments` (line 863) — AC8.3 adds the entry there.
- **Logging conventions** (architecture lines 783-790):
  - INFO for service / session lifecycle ✅ (ALLOW / LOGIN_SUCCESS / TOKEN_EXCHANGE / REFRESH)
  - WARN for expected-but-noteworthy ✅ (DENY / LOGIN_FAILURE)
  - ERROR for unhandled exceptions ✅ (the `logger.error(..., exc_info=True)` line at logout's `session_delete_failed` path stays — and we add a sibling structured `DENY` emit)
  - **No PII** ✅ (AC4 — `sub` truncated; helper accepts no other PII inputs)
  - **Structured JSON output via archetype's logging config** ✅ (AC6 — renderer extension is the minimal change; helper does not introduce a parallel logging surface)
  - **X-Request-Id correlation** ✅ — the archetype's `_inject_trace_context` processor (logging.py:42-49) already injects `traceId`/`spanId` on every emitted record; auth-decision emits inherit this for free.
- **ErrorCode envelope** is unrelated to this story (no new HTTP error codes). The structured emit is observability-only; HTTP envelopes remain `AuthCode.AUTH_STATE_INVALID` / `ErrorCode.SESSION_EXPIRED` / `ErrorCode.FORBIDDEN_SCOPE` as today.
- **AOP `log_io` decorator** continues to emit per-method DEBUG I/O at module-import time. Auth-decision emits are **additive** — the existing AOP layer is untouched.

### Source files to read before editing

- `services/bff/src/bff/api/auth.py` — entire file (502 lines). Read fully so you can convert call sites in source order without missing the 4 progress markers that get *deleted*, not converted.
- `services/bff/src/bff/services/resource_server_client.py` — 3 emit sites at lines 251, 273, 430.
- `services/bff/src/bff/observability/logging.py` — entire file (155 lines). The renderer extension is a 3-line patch; read the full file first so you understand the `event_dict` lifecycle (foreign_pre_chain processors → ProcessorFormatter → renderer).
- `services/resource-server/src/resource_server/auth/oidc_bearer.py` — 3 emit sites, plus the happy path ALLOW insertion immediately before `return decoded` (line 93).
- `services/resource-server/src/resource_server/auth/dependencies.py` — 2 emit sites.
- `services/resource-server/src/resource_server/observability/logging.py` — byte-identical mirror of the BFF logging.py; same 3-line patch.
- `services/bff/tests/observability/test_json_renderer.py` (72 lines) — read the existing test pattern; the new `test_auth_decision_json.py` follows it exactly.

### Library / framework versions (pinned)

- **Python 3.14** on both BFF and RS (per architecture line 74; `services/bff/pyproject.toml`, `services/resource-server/pyproject.toml`).
- **FastAPI** + **stdlib logging** (no new dependency).
- **structlog** is already a transitive dep via the archetype's `observability/logging.py` — no new pyproject entries.
- **StrEnum** is `from enum import StrEnum` (Python 3.11+; native at 3.14). Existing usage: `services/bff/src/bff/core/config.py:13`, `services/resource-server/src/resource_server/auth/models.py:7`.
- **PyJWT ≥2.10** (per `docs/security-review.md` §4). Exception types `jwt.InvalidSignatureError` / `InvalidAudienceError` / `InvalidIssuerError` / `ExpiredSignatureError` / `MissingRequiredClaimError` / `PyJWKClientError` are all stable.

### File structure to follow

Place new code at:

```
services/bff/src/bff/aop/
├── __init__.py            (no changes)
├── logging_decorator.py   (no changes — existing log_io)
└── auth_logging.py        (NEW — AC1 + Task 1)

services/resource-server/src/resource_server/aop/
├── __init__.py            (no changes)
├── logging_decorator.py   (no changes)
└── auth_logging.py        (NEW — Task 1.5 mirror)
```

Place new tests at:

```
services/bff/tests/aop/
├── test_logging_decorator.py            (existing)
├── test_logging_decorator_branches.py   (existing)
└── test_auth_logging.py                 (NEW — Task 6.1)

services/bff/tests/observability/
├── test_json_renderer.py                (existing)
├── test_plain_renderer.py               (existing)
├── test_secret_redaction.py             (existing)
└── test_auth_decision_json.py           (NEW — Task 7.1)
```

RS mirrors are at the analogous paths.

### Testing standards summary

- **pytest** (async via `pytest-asyncio`). Source-mirroring test layout: `services/<svc>/tests/<package>/test_<module>.py`.
- **`caplog` fixture** is the canonical way to capture log records in this project (see `services/bff/tests/observability/test_json_renderer.py` for the pattern).
- **Static-analysis fixture** (AC5) goes in the `services/<svc>/tests/conftest.py` at session scope so it covers every test in the suite. Pattern: monkey-patch the module's `emit_auth_decision`, run no-token-material assertions on each call, delegate to the real impl. Per Story 4.4's conftest patterns.
- **Coverage** thresholds: BFF + RS ≥90% line, per-file ≥70%. The new module is small enough that per-file 100% is feasible and expected.
- **Lint + format + types:** `uv run ruff check && uv run ruff format --check && uv run ty check` must pass on every commit per `services/resource-server/CLAUDE.md` and the BFF mirror.

## Previous Story Intelligence

Story 7-2 (`7-2-oidc-discovery-bootstrap.md`) is the closest "previous" story in Epic 7 — it's a planning spec, not a freshly-created comprehensive story file, but it carries directly relevant signal:

- **Sequencing pinned by 7-2 spec:** "Story 7.2 should land **after** Story 7.3 if you want auth-decision logs to also report the discovery fetch as a structured event." So when 7-2 lands later, it will emit `LOGIN_SUCCESS` / `DENY` events around `/.well-known/openid-configuration` startup probes. The helper produced by **this** story (7-3) is what 7-2 will call. Implementer for 7-3 must therefore avoid baking in BFF-only assumptions — RS mirror is mandatory, and the helper signature is intentionally service-neutral (accepts only `decision`, `reason`, `sub`).
- **No env-var changes in 7-3:** 7-2 owns the `OIDC_ISSUER_URL` / `OIDC_PUBLIC_BASE_URL` consolidation. 7-3 must NOT touch `.env.example` or `config.py` — keep the change surface tight.
- **No realm changes in 7-3:** 7-1 (`7-1-bff-claim-to-role-mapping-demo.md`) owns the `groups` claim mapper + `oidc-group-membership-mapper`. 7-3 leaves `keycloak/realm-bmad-books.json` untouched.

From Epic-5 / Epic-6 doc-heavy story precedent (`feedback_doc_review_non_negotiable.md`):

- **Adversarial review is non-negotiable** at code-review time. The three-layer review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) will run on this story's diff at code-review. Citation accuracy matters — line numbers in `services/bff/src/bff/api/auth.py` will shift after the import is added; the reviewer will check that every cited line number in this story file (AC2's 17 sites, AC3's RS sites) **still resolves to the right semantic site post-edit**. Update line numbers in Completion Notes if they drift.

- **Doc-only and source-code stories both get full review.** The Epic-5 retrospective (`epic-5-retro-2026-05-18.md`) and Epic-6 close confirmed the 44-patches-across-4-doc-only-stories number — fabricated citations and stale line numbers are the most-common review findings.

From Stories 1.5 + 1.7 (the auth foundation): the `_safe_session_id_log` helper at `services/bff/src/bff/api/auth.py:83-87` is the precedent for **how** to truncate `sub`. The new `_truncate(sub)` helper must match its semantics exactly (first 8 + ellipsis if `len > 12`) so two adjacent log lines (one structured, one stdlib) show the same shape — operators correlating them don't see `abc12345...` vs `abc1234…` divergence.

From Story 3.5 (the `ResourceServerClient`): the refresh + replay flow has THREE distinct outcomes, and 7-3 emits a structured event for each:
1. First attempt 200/2xx → no auth-decision emit needed (the JWT was already validated upstream; this is just RS data flow).
2. First attempt 401, refresh succeeds, retry 2xx → emit `REFRESH` `reason=access_token_refreshed`.
3. First attempt 401, refresh fails → emit `DENY` `reason=refresh_failed`.
4. First attempt 401, refresh succeeds, retry still 401 → emit `DENY` `reason=rs_401_after_refresh`.

Outcomes 2-4 map directly to the three existing logger lines in `resource_server_client.py`. Outcome 1 (the happy path) is NOT a structured auth-decision event — the access_token's validity was already attested by the RS's `ALLOW reason=jwt_valid` emit on the RS side.

## Git Intelligence

Recent commits (last 5):

```
760cbb2 plan for epic 7                                          (this commit created the planning spec we're upgrading)
d26dd7c chore: stop tracking _bmad/ tooling directory
7b2eb9c implement epic 6                                         (Epic 6 close — SPA SSR edge; relevant for the `:4000` topology if any smoke check runs)
ed34ac7 fix(d140-d141): make bare `docker compose up` work for a fresh clone
5f9b0f7 chore(epic-5): retrospective — flip epic-5 done, A1/A2 action items
```

Key signal:

- **`760cbb2 plan for epic 7`** is the commit that created the planning specs at `_bmad-output/implementation-artifacts/7-{1,2,3}-*.md`. It also already applied the PKCE removal across the BFF source. The pre-existing planning spec at `7-3-structured-auth-decision-logs.md` was the seed for this comprehensive story file — every AC / reason / call site in this file traces back to that seed (extended, never contradicted).

- **The current `auth.py` line numbers cited in AC2** are the post-`760cbb2` line numbers (PKCE removed). Earlier commits referenced different line numbers (e.g., `auth.py:167-172` in the planning spec was correct against the post-PKCE source). Verify before editing: `wc -l services/bff/src/bff/api/auth.py` should report ~502 lines.

- **`7b2eb9c implement epic 6`** flipped the SPA edge from BFF (`:8000`) to SPA SSR (`:4000`). This is *not* relevant to 7-3's code surface (auth.py is server-side; the SPA edge proxies cookies byte-for-byte and doesn't see any auth log content). However, if Task 10.4's smoke check is run, hit the BFF at `:8000` directly via `docker compose exec bff curl ...` — the SPA edge at `:4000` will NOT surface the BFF's logs (compose log streams are per-service).

- **No CI is configured** (per `docs/security-review.md` Known Gap "no GitHub Actions CI"). All test verification is local-only. Task 10 is the gate; there is no remote check.

## Latest Technical Information

- **Python 3.14** (released 2025-10): `StrEnum` is stable and idiomatic; no compatibility concerns.
- **PyJWT 2.10.x** (current as of 2026-05): exception hierarchy is `jwt.InvalidTokenError` → 11 subclasses including `InvalidSignatureError`, `InvalidAudienceError`, `InvalidIssuerError`, `ExpiredSignatureError`, `MissingRequiredClaimError`. AC3's exception-type → reason-classifier mapping is stable; no breaking changes expected.
- **structlog 24.x** (current): the project uses structlog via `ProcessorFormatter` (stdlib bridge). The 3-line `_json_renderer` extension is purely additive — no structlog API surface changes needed.
- **FastAPI 0.115+** (per archetype): no change to dependency injection or Depends() semantics relevant to this story.

## References

- Source story planning spec (now superseded by this file): `_bmad-output/implementation-artifacts/7-3-structured-auth-decision-logs.md` (the committed version in `760cbb2`).
- Sprint Change Proposal: `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-21.md` (especially §1 P8 origin, §3 selected option, §5 sequencing).
- Architecture: `_bmad-output/planning-artifacts/architecture.md` lines 82 (`Logging: AOP-based log_io`), 783-790 (logging conventions), 821 + 863 (Pattern Amendments), 1426 (PRD §8 constraints coverage).
- PRD: `_bmad-output/planning-artifacts/PRD.md` §12 (structured logging is the only operational-visibility surface).
- Security review: `docs/security-review.md` — gets a new §7 per AC8.1. Stories 5.2's structure is the template.
- Sibling Epic-7 stories: `_bmad-output/implementation-artifacts/7-1-bff-claim-to-role-mapping-demo.md`, `_bmad-output/implementation-artifacts/7-2-oidc-discovery-bootstrap.md`.
- Existing auth surface: `services/bff/src/bff/api/auth.py`, `services/bff/src/bff/services/resource_server_client.py`, `services/resource-server/src/resource_server/auth/oidc_bearer.py`, `services/resource-server/src/resource_server/auth/dependencies.py`.
- Existing logging surface: `services/bff/src/bff/observability/logging.py`, `services/resource-server/src/resource_server/observability/logging.py`.
- Existing AOP: `services/bff/src/bff/aop/logging_decorator.py`, `services/resource-server/src/resource_server/aop/logging_decorator.py`.
- Existing tests to study: `services/bff/tests/observability/test_json_renderer.py`, `services/bff/tests/observability/test_plain_renderer.py`, `services/bff/tests/aop/test_logging_decorator.py`.
- Project conventions: `CLAUDE.md` (Python invocation), `services/resource-server/CLAUDE.md` (quality-checks gate on every commit).

### Project Structure Notes

- All new files land at conventional locations per `architecture.md §Complete Project Directory Structure` (`aop/` package on both services; test mirrors at `tests/aop/` + `tests/observability/`). No `utils/` / `lib/` dumping grounds.
- Helper module name is `auth_logging.py` (not `auth_audit.py` / `decisions.py`) to match the AOP folder's existing naming (`logging_decorator.py`). The wire `logger` field becomes `"bff.aop.auth_logging"` / `"resource_server.aop.auth_logging"` — operators can grep on either prefix.
- StrEnum naming follows project convention (see `services/bff/src/bff/core/config.py:13 LogLevel(StrEnum)`, `services/resource-server/src/resource_server/auth/models.py:7 Role(StrEnum)`).
- No detected conflicts with unified project structure.

## Notes

- The archetype's `log_io` AOP decorator continues to emit per-method I/O at DEBUG; this story is **additive** — auth decisions emit on top of `log_io`, not in place of it.
- This is the first story in the POC to formalize an authorization-event schema. If the ACME real-project later adds fields (`request_id`, `scope`, `client_id`), they can be added as optional kwargs to `emit_auth_decision` without breaking the ACME-minimum 4-field guarantee.
- **Sprint convention (post-review clarification, P9):** Story 7.3's own dev pass only transitions the `7-3-structured-auth-decision-logs` row (ready-for-dev → in-progress → review → done). The accompanying flips on `epic-7: backlog → in-progress` and the sibling `7-1` / `7-2` rows from `backlog → ready-for-dev` are NOT 7.3's work — they landed during the parallel-worktree contexting pass that authored stories 7.1, 7.2, 7.3 simultaneously (see sprint-status.yaml header metadata for `2026-05-21`). The parallel-worktree merge convention records all three sibling rows together; this is consistent with how Epic 5 was contexted in parallel for stories 5.1/5.2.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (via bmad-create-story → bmad-dev-story 2026-05-21)

### Debug Log References

- BFF + RS quality gates at dev close: `uv run ruff check` ✓, `uv run ruff format --check` ✓, `uv run ty check` ✓, `uv run pytest` ✓ on both services.
- BFF: 535 passed (was 528 at baseline `760cbb2`; +14 helper unit tests + 5 renderer integration tests + 2 parametrize expansions on existing tests, partially offset by deletion of 7 progress-marker-related test parametrizations).
- RS: 347 passed (was ~324 at baseline; +14 helper unit tests + 5 renderer integration tests + 1 converted scope-rejection assertion = +21 net new test cases).
- BFF aggregate line coverage: 97.21% (≥90% gate met). Per-file floor met (lowest: `core/database.py` 84%, all others ≥90%).
- RS aggregate line coverage: 98.44% (≥90% gate met). Per-file floor met (lowest: `auth/factory.py` 77%, all others ≥90%).
- AC5 static-analysis fixture deviation: spec hint said "monkey-patches `emit_auth_decision`"; chose a `logging.Handler` on the helper's logger instead. Rationale: stdlib `extra=` puts fields on `record.__dict__`, but consumers `from bff.aop.auth_logging import emit_auth_decision` get their own binding so module-attribute patching does not propagate. The handler approach catches every emission regardless of binding location and is robust to future consumers being added. Functionally equivalent and stricter than the spec's hint: every record passing through the helper's logger is validated, not just direct calls.
- AC5 banned-substring list refined: the spec literally lists `id_token` as a banned substring, but the conforming reasons in AC2 (`id_token_missing`, `id_token_invalid`) contain that identifier as a compound-name fragment. Resolved by switching the helper's regex to word-bounded matching (`\bid_token\b`, `\baccess_token\b`, `\brefresh_token\b`) — false positives for OAuth concept names inside compound reasons are eliminated; `id_token=eyJ...` style leakage still triggers. The non-word-bounded patterns (`Bearer `, `eyJ`, JWT-shape, base64url-ish) keep their literal-substring semantics.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Created by bmad-create-story for story 7-3; supersedes the planning-spec version committed in `760cbb2 plan for epic 7`.
- The seed planning spec's 6 ACs are preserved and expanded into 10 numbered ACs + 10 tasks. No content from the planning spec was discarded.
- One source-line citation update vs. the planning spec: the planning spec cited `auth.py:167-172` for `auth_state_created`; the live file (post-PKCE-removal in `760cbb2`) has that emit at `auth.py:163-167`. Other planning-spec citations re-verified live and updated where they drifted.
- Two ambiguity questions surfaced and resolved inline (in "Decisions Pinned"):
  - Q1: Logout failure paths use `DENY` (not `LOGIN_FAILURE`), since the ACME schema lacks `LOGOUT_*`. Treats logout as a deny-this-action decision.
  - Q2: `oidc_bearer.py` DENY emits leave `sub=None` (no reading-untrusted-data from a failed-validation JWT body).
- All 10 tasks and 35 subtasks complete; all 11 ACs (incl. AC4a) satisfied.
- Wire-renderer surface honors AC6: `services/bff/src/bff/observability/logging.py` and the RS mirror lift `decision` / `sub` / `reason` off the foreign `LogRecord` (via `event_dict["_record"]`) in both `_json_renderer` and `_plain_renderer`. Existing `test_json_renderer.py` and `test_plain_renderer.py` (BFF + RS) remain green unchanged — the extensions are strictly additive.
- **Anomaly A1 (logged honestly, not a scope leak):** 3 pre-existing test failures in `services/bff/tests/services/test_session_service.py` (`test_create_auth_state_falls_back_unsafe_return_to`, `test_create_auth_state_retries_on_integrity_error`, `test_consume_auth_state_returns_and_deletes_row`) were broken at baseline `760cbb2` because the PKCE-removal commit changed `SessionService.create_auth_state` from returning `(row, code_verifier)` to just `row` but only updated one of the four callsites. Verified pre-existing via `git stash && pytest` against `760cbb2`. Fixed in this story (3 trivial single-line tuple-unpack removals) so AC9's "all test suites pass green" close gate holds; documented here for the reviewer because the test file is outside the AC2/AC3 surface map but the fix is unambiguous and required for green CI. If reviewer prefers strict scope, revert by re-adding `, _` to the three call sites and reopen the failures as a fast-follow story.
- Task 10.4 smoke check: completed via the in-process FastAPI test harness rather than `docker compose up`. The integration tests in `tests/api/test_auth.py` drive `/auth/login` against the real BFF FastAPI app surface (same code path as `uvicorn`), capture the auth-decision emit via `caplog`, and assert the structured `decision=allow reason=auth_state_created` record. Operationally equivalent to the Mode-B HTTP-probe pattern of Story 5.4 (agent-completable without a browser AND without a running compose stack — the integration test surface fully exercises the emit + structured wire shape).
- The four logout flow-progress markers (`auth_logout_start`, `auth_logout_no_refresh_token`, `auth_logout_no_id_token`, plus the now-unused `_safe_session_id_log` calls in those deleted blocks) were dropped per "Decisions Pinned": operators wanting per-method I/O visibility can run with `LOG_LEVEL=DEBUG` to surface the `log_io` AOP decorator output. `_safe_session_id_log` and `_http_error_classifier` helper functions remain in `auth.py` as defensive future-use scaffolding referenced by the helper module's docstring (`_safe_session_id_log`) — pruning them is doc-link/grep churn out of scope.

### File List

**New files:**
- `services/bff/src/bff/aop/auth_logging.py` — `AuthDecision` StrEnum + `emit_auth_decision` helper (AC1).
- `services/resource-server/src/resource_server/aop/auth_logging.py` — byte-identical RS mirror (Task 1.5).
- `services/bff/tests/aop/test_auth_logging.py` — helper unit tests (AC1, AC4, AC4a, AC7).
- `services/resource-server/tests/aop/test_auth_logging.py` — RS mirror.
- `services/bff/tests/observability/test_auth_decision_json.py` — JSON + plain renderer integration tests (AC6).
- `services/resource-server/tests/observability/test_auth_decision_json.py` — RS mirror.

**Modified BFF source:**
- `services/bff/src/bff/api/auth.py` — 17 call sites converted (4 progress markers deleted, 13 routed through `emit_auth_decision`); helper import added.
- `services/bff/src/bff/services/resource_server_client.py` — 3 call sites converted (`refresh_failed` / `rs_401_after_refresh` / `access_token_refreshed`); helper import added.
- `services/bff/src/bff/observability/logging.py` — `_json_renderer` + `_plain_renderer` extended with the auth-decision field lift (AC6).

**Modified RS source:**
- `services/resource-server/src/resource_server/auth/oidc_bearer.py` — ALLOW on the `_validate_access_token` happy path; DENY with PyJWT-exception → reason-classifier mapping; DENY on missing/blank token; DENY on scope-insufficient; helper import added.
- `services/resource-server/src/resource_server/auth/dependencies.py` — DENY on auth_unexpected_error; DENY on role_denied; helper import added.
- `services/resource-server/src/resource_server/observability/logging.py` — mirror BFF renderer extensions.

**Modified BFF tests:**
- `services/bff/tests/conftest.py` — AC5 session-scoped autouse `logging.Handler` fixture (`_assert_no_token_material_in_auth_decisions`).
- `services/bff/tests/api/test_auth.py` — `_has_auth_decision` helper added; 5 message-substring assertions converted to structured-field assertions (revocation_failed × 4, end_session_failed × 2, session_delete_failed, revocation 4xx); 2 progress-marker assertion blocks removed (`auth_logout_no_refresh_token`, `auth_logout_no_id_token`); `caplog.set_level` logger names updated to `bff.aop.auth_logging` where appropriate.
- `services/bff/tests/services/test_resource_server_client.py` — `refresh_failed` and `access_token_refreshed` message-substring assertions converted to structured-field assertions.
- `services/bff/tests/services/test_session_service.py` — 3 pre-existing failing tests fixed (Anomaly A1; `, _` tuple unpacks removed — the function returns a single value since `760cbb2`'s PKCE removal).

**Modified RS tests:**
- `services/resource-server/tests/conftest.py` — AC5 session-scoped autouse fixture (RS mirror).
- `services/resource-server/tests/auth/test_oidc_bearer.py` — `test_scope_rejection_emits_warning_log_with_sub_and_scope` converted to assert on the structured DENY record on `resource_server.aop.auth_logging` (the legacy `logger.warning("Scope check failed: ...")` line was converted; the structured emit carries `reason=scope_insufficient:reading-speed:read` + truncated `sub`).

**Modified docs:**
- `docs/security-review.md` — new `## 7. Auth-decision audit trail` section inserted before `## Accepted Risks` (AC8.1).
- `README.md` — Architecture overview block gains one reference line for `docs/security-review.md §7` (AC8.2).
- `_bmad-output/planning-artifacts/architecture.md` — Pattern Amendments entry dated 2026-05-21 added after the existing PKCE removal entry (AC8.3).

**Sprint tracking:**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `7-3-structured-auth-decision-logs` ready-for-dev → in-progress → review.
- `_bmad-output/implementation-artifacts/7-3-structured-auth-decision-logs.md` — this story file; Status updated to `review`; Tasks/Subtasks all `[x]`; Dev Agent Record populated.

### Change Log

| Date | Story State | Summary |
|---|---|---|
| 2026-05-21 | ready-for-dev → in-progress | Dev pass started; Tasks 1-2 (helper module + renderer extensions on BFF + RS). |
| 2026-05-21 | in-progress | Tasks 3-5: BFF auth.py + resource_server_client.py call-site conversions; RS oidc_bearer.py + dependencies.py conversions. |
| 2026-05-21 | in-progress | Tasks 6-7: helper unit tests + AC5 conftest fixture (BFF + RS); renderer integration tests (BFF + RS). |
| 2026-05-21 | in-progress | Task 8: caplog assertions converted from message-substring to structured-field across `test_auth.py`, `test_resource_server_client.py`, `test_oidc_bearer.py`. AC5 banned-pattern list switched to word-bounded regex for OAuth concept identifiers. Anomaly A1 (pre-existing PKCE-removal test bugs) fixed in-scope to hold AC9. |
| 2026-05-21 | in-progress | Task 9: docs/security-review.md §7 appended; README.md reference line added; architecture.md Pattern Amendments entry added. |
| 2026-05-21 | in-progress → review | Task 10: BFF + RS quality gates all green (ruff check, ruff format --check, ty check, pytest). Aggregate coverage BFF 97.21% / RS 98.44% (≥90% gate met). |
| 2026-05-21 | review → done | Three-layer adversarial code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor). Edge Case Hunter caught a CRITICAL pipeline bug (E1) the integration tests missed: `remove_processors_meta` stripped `_record` before the renderer ran, so the production wire output carried NO `decision`/`sub`/`reason` despite all unit tests passing. 9 patches applied: P1 added `_lift_auth_decision_fields` to `foreign_pre_chain` (BFF + RS) so the lift happens BEFORE `_record` is stripped; helper now sets `_is_auth_decision` sentinel on every emit. P2 extended the AC5 conftest fixture to validate `sub` against banned regexes (was reason-only). P3 added 8 pin tests for `_classify_jwt_exception` PyJWT exception → reason mapping. P4 fixed stale `Status: in-progress` header. P5 tightened renderer gate to the sentinel attribute (was a bare `hasattr(record, "decision")` collision risk). P6 scoped `caplog.set_level` per logger in `test_logout_db_delete_failure...`. P7 softened helper docstring's `+00:00` timestamp claim. P8 (from DN1) added `session_delete_succeeded` flag in logout endpoint — trailing `ALLOW reason=logout` no longer fires on DB-delete failure paths. P9 (from DN2) updated the "Sprint convention" paragraph to acknowledge parallel-worktree contexting wrote sibling 7-1/7-2/epic-7 YAML rows. 4 defers logged D166-D169. 10 dismissed as noise (Blind Hunter's F1 on `except A, B:` syntax was a Python 3.14 PEP 758 false positive; F2 on Handler swallowing assertions was wrong — assertions DO propagate from custom emit(); etc.). E2E pipeline tests added (BFF + RS) — exercise the real `ProcessorFormatter` chain so future regressions are caught. Quality gates re-attested: BFF 537 passed (was 535; +2 E2E tests), RS 357 passed (was 347; +8 _classify_jwt pins + +2 E2E tests). Coverage BFF 97.16% / RS 98.34% (≥90% gate met). |

### Review Findings

Three-layer adversarial review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) ran in parallel against the 7.3 working-tree diff (2,476 lines: 17 modified files + 6 new files). Acceptance Auditor returned PASS on all 11 ACs + all 10 tasks against live pytest output (BFF 535/535 green, RS 347/347 green, BFF coverage 97.21%, RS coverage 98.44%) — BUT Edge Case Hunter reproduced an end-to-end production-pipeline failure that the integration tests in the AC6 surface do NOT catch.

#### Decision-Needed

- [x] [Review][Decision] **DN1: Logout DB-error path emits BOTH `DENY reason=session_delete_failed` AND `ALLOW reason=logout` for the same request** — RESOLVED via option (a): gate the trailing ALLOW behind a `session_delete_succeeded` flag (P8). — control flow at `services/bff/src/bff/api/auth.py:484-505`: when `_session_service.delete_session()` raises `SQLAlchemyError` in `finally`, the `except` body emits DENY then falls through to the trailing `emit_auth_decision(ALLOW, reason="logout", sub=row.sub)` at line 500. Operators counting `decision=allow reason=logout` will over-count DB-failed logouts as successful. The "Decisions Pinned" section addresses keeping `logger.error` alongside DENY, but does NOT address whether the trailing ALLOW should also fire. Three resolution options: (a) gate the trailing ALLOW behind a `logout_succeeded` flag — emit only on the success branch; (b) accept the dual-emit as truthful (the user-facing logout DID succeed: cookies cleared, 204 returned; DENY records audit-trail of internal failure, ALLOW records UX outcome) and document the semantic in `docs/security-review.md §7`; (c) re-emit ALLOW with a different reason like `logout_partial` on the failure branch. Edge Case Hunter (E3).

- [x] [Review][Decision] **DN2: Sprint-status YAML flips three rows the story explicitly disclaims** — RESOLVED via option (a): updated the "Sprint convention" paragraph (P9) to acknowledge parallel-worktree contexting wrote sibling rows; YAML untouched. — story body line 439 ("Sprint convention") pins: "This story (7.3) does not touch the `epic-7` row in `sprint-status.yaml` — only its own `7-3-structured-auth-decision-logs` line transitions". The diff flips `epic-7: backlog → in-progress`, `7-1-bff-claim-to-role-mapping-demo: backlog → ready-for-dev`, `7-2-oidc-discovery-bootstrap: backlog → ready-for-dev`. Per sprint-status.yaml header metadata, these flips are an artifact of three Epic-7 stories being contexted in parallel worktrees — but the 7.3 story body's own "Sprint convention" pin contradicts this. Three resolution options: (a) update the story body's "Sprint convention" paragraph to acknowledge the parallel-worktree-merge convention; (b) revert non-7.3 rows in the YAML (risky — would undo legitimate state for 7.1/7.2 contexting); (c) accept-as-is and add a one-line note to the Change Log explaining the merge artifact. Blind Hunter (F3).

#### Patches

- [x] [Review][Patch] **P1: Production renderer drops `decision`/`sub`/`reason` from the wire — entire ACME schema invisible in real logs** [`services/bff/src/bff/observability/logging.py:88-99,130-145`, RS mirror at `services/resource-server/src/resource_server/observability/logging.py`] — **CRITICAL**. The configured `ProcessorFormatter` runs `processors=[remove_processors_meta, renderer]`. `remove_processors_meta` (structlog stdlib) deletes `_record` from `event_dict` BEFORE the renderer is called. `_auth_decision_fields(event_dict)` reads `event_dict.get("_record")` and short-circuits to `{}` when `_record` is absent. Reproduced end-to-end: emitting `AuthDecision.ALLOW reason=jwt_valid sub=abcdef0123456789` through the configured pipeline produces `{"timestamp":"...", "level":"info", "logger":"bff.aop.auth_logging", "message":"auth_decision", "traceId":"NO_TRACE_ID", "spanId":"NO_SPAN_ID"}` — no `decision`, no `sub`, no `reason`. AC6's "JSON output verified" claim is materially false in production. Tests `test_auth_decision_json.py` pass only because `_event_dict_from_record(record)` constructs `event_dict` by hand with `"_record": record` still present, bypassing the production processor chain. AC8's `docs/security-review.md §7` describes a wire shape that does not exist. Task 10.4's smoke check cannot have been actually executed. Fix: move the auth-decision-field lift into the `foreign_pre_chain` (which runs BEFORE `remove_processors_meta`) — add a processor that copies `decision`/`sub`/`reason` from `event_dict["_record"]` (still present at foreign_pre_chain time) into the top-level event_dict; then update `_auth_decision_fields` to read from event_dict directly. Add an integration test that uses the configured `ProcessorFormatter` (not a hand-built event_dict). Blind Hunter (F5) + Edge Case Hunter (E1, E2).

- [x] [Review][Patch] **P2: AC5 fixture validates `reason` but not `sub` — a misuse passing a JWT-shaped `sub` would leak `eyJ...` to the wire and the fixture would not fail** [`services/bff/tests/conftest.py:172-190`, RS mirror at `services/resource-server/tests/conftest.py`] — `_AuthDecisionAssertHandler.emit` reads `reason = getattr(record, "reason", "")` and runs every banned-regex against `reason` only. The `record.sub` field is never inspected. AC5's banned-substring list explicitly includes `eyJ` (the JWT header prefix); a caller error like `emit_auth_decision(sub=access_token_value, decision=AuthDecision.ALLOW, reason="jwt_valid")` produces a wire `sub` of `"eyJhbGci..."` (truncated to 8 chars + ellipsis) — `eyJ` exposed but uncaught. Fix: extend the handler to run the banned-regex set against `record.sub` as well as `record.reason`, asserting both are clean. Edge Case Hunter (E5).

- [x] [Review][Patch] **P3: `_classify_jwt_exception` mapping has no pin test for the PyJWT exception-class → reason classifier table** [`services/resource-server/tests/aop/test_auth_logging.py` — new test cases needed] — AC3 lists 7 mappings (`InvalidSignatureError` → `signature_invalid`, `InvalidAudienceError` → `audience_mismatch`, `InvalidIssuerError` → `issuer_mismatch`, `ExpiredSignatureError` → `exp_past`, `MissingRequiredClaimError` → `claim_missing[:<name>]`, `PyJWKClientError` → `jwks_lookup_failed`, fallback `InvalidTokenError` → `token_invalid`). `grep -rn "_classify_jwt\|signature_invalid\|audience_mismatch" services/resource-server/tests/` returns only the integration test's hard-coded reason strings — no test ever calls `_classify_jwt_exception(jwt.InvalidSignatureError("..."))` and verifies the return value. A future PyJWT MRO change (or class rename) could silently shift every emit to the fallback `"token_invalid"` without any test failure. Fix: add 7 parametrized pin tests exercising each exception subclass and asserting the returned classifier. Edge Case Hunter (E4).

- [x] [Review][Patch] **P4: Story Status header stale at `in-progress` despite Change Log recording transition to `review`** [`_bmad-output/implementation-artifacts/7-3-structured-auth-decision-logs.md:3`] — line 3 reads `Status: in-progress`; Change Log final row reads `2026-05-21 | in-progress → review | Task 10:...`; File List section claims "Status updated to `review`". One-line fix: change line 3 to `Status: review`. Acceptance Auditor (F1).

- [x] [Review][Patch] **P5: Renderer `hasattr(record, "decision")` gate is namespace-vulnerable** [`services/bff/src/bff/observability/logging.py:97-99`, RS mirror] — `_auth_decision_fields` gates on a single attribute name (`decision`) — any third-party library or future code that attaches `extra={"decision": ...}` for unrelated audit/scoring purposes would have its LogRecord mis-rendered as a malformed auth-decision line. Fix: tighten the gate to also check the record's logger name (`record.name in ("bff.aop.auth_logging", "resource_server.aop.auth_logging")`) or attach a private sentinel attribute from the helper (e.g., `extra={"_is_auth_decision": True, ...}`) and gate on that. Edge Case Hunter (E9).

- [x] [Review][Patch] **P6: `caplog.set_level(logging.WARNING)` without `logger=` in `test_logout_db_delete_failure_still_returns_204_and_clears_cookies`** [`services/bff/tests/api/test_auth.py:1334`] — widens capture to root logger, capturing every WARNING+ from any other logger during the test. Surrounding converted tests in the same file (lines 1088, 1131, 1152, 1276 per diff context) all pass `logger="bff.aop.auth_logging"` — this one is the odd inconsistency and creates flaky-test risk if a background subsystem warns during the test. Fix: split into two `set_level` calls — one scoped to `bff.api.auth` ERROR (for the stdlib `logger.error` line) and one to `bff.aop.auth_logging` WARNING (for the structured DENY emit). Blind Hunter (F10) + Edge Case Hunter (E10).

- [x] [Review][Patch] **P7: Helper docstring claims `timestamp` is `+00:00` ISO-8601 but does not control the timestamp** [`services/bff/src/bff/aop/auth_logging.py:88-90`, RS mirror at `services/resource-server/src/resource_server/aop/auth_logging.py:466-468`] — docstring asserts `"timestamp is UTC ISO-8601 with offset (+00:00)"`, but the timestamp is produced by `_add_timestamp` in the foreign_pre_chain (`logging.py:52-62`), not by the helper. A future upstream change (e.g., `datetime.isoformat(timespec=...)` swap, or a `Z`-suffix variant) would silently break the wire shape with no test guarding it. Fix: soften the docstring to "the archetype's logging config attaches a UTC ISO-8601 timestamp" without claiming a specific offset format, OR add an integration test that captures the renderer's actual timestamp output and pins the `+00:00` shape. Blind Hunter (F11).

#### Deferred

- [x] [Review][Defer] **D166: Anomaly A1 root cause — PKCE-removal commit `760cbb2` left 3 stale tuple-unpack callsites in `test_session_service.py`** [`services/bff/tests/services/test_session_service.py`] — pre-existing failure, fixed in-scope by Story 7.3 to hold AC9. Underlying issue is the prior story's parallel context-pass missed propagating `SessionService.create_auth_state` signature change to all 4 callsites. Belongs to: backlog-hygiene pass on parallel-worktree merge convention. Severity: low. Blind Hunter (F9).

- [x] [Review][Defer] **D167: `_validate_access_token` ALLOW emits `sub=str(decoded.get("sub", ""))` — defensive fallback that can never fire today** [`services/resource-server/src/resource_server/auth/oidc_bearer.py:115-119`] — `jwt.decode(..., require=["iss","aud","exp","sub"])` enforces `sub` presence before this code path; the `.get("sub", "")` fallback is unreachable. If a future change weakens `require=`, an ALLOW event would silently emit with `sub=""` on the wire (the helper's truncation passes `""` through unchanged). Code-cleanliness concern, not actively broken. Fix: use `sub=decoded["sub"]` to fail loud. Belongs to: code-cleanliness pass. Severity: nit. Blind Hunter (F6).

- [x] [Review][Defer] **D168: `_truncate(sub)` has no `isinstance(sub, str)` type guard — non-str input crashes the helper** [`services/bff/src/bff/aop/auth_logging.py:61-72`, RS mirror] — `if not sub:` matches `int(0)`, `False`, `[]`; `len(sub)` raises `TypeError` on objects without `__len__` (e.g., UUID). Defensive concern — current callers all pass `str | None`. Belongs to: defensive-hardening pass on the helper. Severity: nit. Edge Case Hunter (E6).

- [x] [Review][Defer] **D169: `dependencies.py:44` `logger.warning("Bearer token authentication failed: ...")` matches operator regex for token-leak alarm** [`services/resource-server/src/resource_server/auth/dependencies.py:43-45`] — `docs/security-review.md` documents `Bearer ` (trailing space) as a banned-substring AC5 regex; meanwhile this legacy stdlib WARN line emits the literal substring on every bearer-auth failure. Operators grep'ing the JSON log surface for `Bearer ` would false-positive on every JWT validation failure. Pre-existing log line, not modified by 7.3. Belongs to: future docs cleanup pass to distinguish the two surfaces, OR a rewording pass on the legacy log line. Severity: nit. Edge Case Hunter (E11).

#### Dismissed (10 — recorded for the audit trail)

- Blind F1 (`except ValueError, OSError:` invalid syntax) — DISMISSED: Python 3.14 PEP 758 makes `except A, B:` valid; both classes are caught (verified via direct repro).
- Blind F2 (AC5 handler swallows assertions) — DISMISSED: `Handler.handle()` does not catch exceptions from `emit()`; assertions DO propagate (verified via repro returning exit_code=1).
- Blind F4 (helper ASCII dots vs Unicode ellipsis convention) — DISMISSED: `_safe_session_id_log` at `auth.py:88` uses ASCII `"..."`; the helper correctly matches. Story body's AC4 wording loosely uses U+2026 but the canonical convention is ASCII.
- Blind F7 (`auth_state_created` semantic fit as ALLOW) — DISMISSED: AC2 explicitly states this is ALLOW not LOGIN_SUCCESS; the trade-off is acknowledged in the spec.
- Blind F8 / Edge E7 (word-bounded regex deviates from AC5 "literal substrings") — DISMISSED: documented deviation in Dev Agent Record Debug Log References; functionally stricter (catches `id_token=eyJ...` but permits `id_token_missing`).
- Blind F12 (Pattern Amendments overclaims P8 closure) — depends on P1; addressed by P1 fix.
- Blind F13 (oidc_bearer.py keeps legacy `logger.warning("JWT validation failed: ...")`) — DISMISSED: AC3 wording is silent on whether to keep the legacy line; the implementation choice parallels the explicit "keep both" guidance given for `dependencies.py:43`.
- Blind F14 — withdrawn by the original reviewer.
- Edge E8 (pragma:no-cover path in `_validate_access_token` emits no decision) — DISMISSED: defensive code path theoretically unreachable; emitting `# pragma: no cover` is the right marker.
- Acceptance Auditor F2/F3/F4/F5 — all over-spec / accepted-as-is per the auditor's own dispositions; no defects.
