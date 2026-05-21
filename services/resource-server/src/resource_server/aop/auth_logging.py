"""Structured auth-decision log emitter (Story 7.3 — ACME-TS principle P8).

The ACME-TS design principles mandate a single 4-field wire shape for every
authorization decision: ``{timestamp, sub, decision, reason}``. This module
is the *only* code path in the Resource Server that emits decision events;
the archetype's JSON formatter inflates each entry to a full structured line
that also carries ``level``, ``logger``, ``traceId``, ``spanId``.

The mirror module lives at ``services/bff/src/bff/aop/auth_logging.py`` —
the BFF surface is byte-identical save for the module-name string the wire
``logger`` field reports.
"""

from __future__ import annotations

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)

# `_safe_session_id_log` (bff/api/auth.py:83-87) uses 8 chars + "..." for any
# value longer than 0. The 12-char threshold here preserves intentionally-short
# test fixture subs verbatim while still ellipsizing realistic Keycloak UUIDs.
_SUB_TRUNCATE_AT = 12
_SUB_PREFIX_LEN = 8
_SUB_ELLIPSIS = "..."

_INFO_DECISIONS: frozenset[str]
_WARNING_DECISIONS: frozenset[str]


class AuthDecision(StrEnum):
    """ACME-TS schema-mandated decision vocabulary.

    The set is intentionally tight — six values cover every authZ outcome in
    the BFF + RS surface. CSRF rejection is transport-integrity, not authZ,
    and stays out (see Story 7.3 Dev Notes). Logout failures map to ``DENY``
    because the ACME schema does not name a ``LOGOUT_*`` value.
    """

    ALLOW = "allow"
    DENY = "deny"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    TOKEN_EXCHANGE = "token_exchange"
    REFRESH = "refresh"


_INFO_DECISIONS = frozenset(
    {
        AuthDecision.ALLOW,
        AuthDecision.LOGIN_SUCCESS,
        AuthDecision.TOKEN_EXCHANGE,
        AuthDecision.REFRESH,
    }
)
_WARNING_DECISIONS = frozenset({AuthDecision.DENY, AuthDecision.LOGIN_FAILURE})


def _truncate(sub: str | None) -> str | None:
    """Apply the `_safe_session_id_log` 8-char-prefix convention to ``sub``.

    ``None`` and empty string pass through unchanged so the JSON wire field
    can carry ``null`` / ``""`` honestly. Anything longer than 12 chars is
    truncated to its first 8 chars plus the project-standard 3-dot ellipsis.
    """
    if not sub:
        return sub
    if len(sub) <= _SUB_TRUNCATE_AT:
        return sub
    return f"{sub[:_SUB_PREFIX_LEN]}{_SUB_ELLIPSIS}"


def emit_auth_decision(
    *,
    decision: AuthDecision,
    reason: str,
    sub: str | None = None,
) -> None:
    """Emit a structured auth-decision log entry per ACME-TS principle P8.

    Wire shape is exactly ``{timestamp, sub, decision, reason}``; the
    archetype's JSON formatter inflates the entry with ``level``, ``logger``,
    ``traceId``, ``spanId``. The archetype's logging config attaches a UTC
    ISO-8601 timestamp via the ``_add_timestamp`` foreign_pre_chain processor.

    Parameters
    ----------
    decision:
        One of the six :class:`AuthDecision` values.
    reason:
        Short classifier (``"jwt_valid"``, ``"signature_invalid"``).
        MUST NOT contain token material — the AC5 conftest fixture re-asserts
        this on every test-suite call.
    sub:
        Subject identifier from the validated JWT, or ``None`` for pre-
        validation paths. Truncated to 8 chars + ellipsis when longer than 12.
    """
    level = logging.INFO if decision in _INFO_DECISIONS else logging.WARNING
    logger.log(
        level,
        "auth_decision",
        extra={
            # `_is_auth_decision` is the sentinel the structlog lift gates on
            # so unrelated `extra={"decision": ...}` records cannot collide.
            "_is_auth_decision": True,
            "decision": decision.value,
            "sub": _truncate(sub),
            "reason": reason,
        },
    )


__all__ = ["AuthDecision", "emit_auth_decision"]
