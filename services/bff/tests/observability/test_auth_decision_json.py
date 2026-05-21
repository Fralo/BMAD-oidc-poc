"""Integration tests for the JSON renderer + auth-decision helper (Story 7.3 AC6)."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import MutableMapping
from typing import Any

import pytest
import structlog

from bff.aop.auth_logging import AuthDecision, emit_auth_decision
from bff.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _add_timestamp,
    _extract_exc_info,
    _inject_trace_context,
    _json_renderer,
    _lift_auth_decision_fields,
    _plain_renderer,
)

_LOGGER_NAME = "bff.aop.auth_logging"

_INFO_DECISIONS = (
    AuthDecision.ALLOW,
    AuthDecision.LOGIN_SUCCESS,
    AuthDecision.TOKEN_EXCHANGE,
    AuthDecision.REFRESH,
)
_WARNING_DECISIONS = (AuthDecision.DENY, AuthDecision.LOGIN_FAILURE)


def _event_dict_from_record(record: logging.LogRecord) -> MutableMapping[str, Any]:
    """Mimic structlog's ProcessorFormatter foreign-record event_dict shape.

    The renderer reads `decision` / `sub` / `reason` from the top-level
    event_dict (post-Story-7.3 review-fix P1); `_lift_auth_decision_fields`
    in the production foreign_pre_chain populates them from
    `event_dict["_record"]` before `remove_processors_meta` strips `_record`.
    To stay faithful to the production pipeline, this helper invokes the lift
    explicitly on the constructed event_dict.
    """
    event_dict: MutableMapping[str, Any] = {
        "_record": record,
        "_from_structlog": False,
        "event": record.getMessage(),
        "level": record.levelname.lower(),
        "logger": record.name,
        "timestamp": "2026-05-21T12:34:56.789012+00:00",
        "traceId": NO_TRACE_ID,
        "spanId": NO_SPAN_ID,
    }
    _lift_auth_decision_fields(None, "", event_dict)
    return event_dict


@pytest.mark.parametrize(
    "decision,expected_level",
    [
        *((d, "info") for d in _INFO_DECISIONS),
        *((d, "warning") for d in _WARNING_DECISIONS),
    ],
)
def test_each_decision_renders_acme_schema(
    decision: AuthDecision,
    expected_level: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every AuthDecision value renders the 6 archetype fields + decision/sub/reason."""
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    sub_value = "session-uuid-xxxxxxxxxxxxxx"
    reason_value = f"smoke_{decision.value}"
    emit_auth_decision(decision=decision, reason=reason_value, sub=sub_value)

    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert len(records) == 1
    record = records[0]

    rendered = _json_renderer(None, expected_level, _event_dict_from_record(record))
    parsed = json.loads(rendered)

    # Six archetype fields.
    for field in ("timestamp", "level", "logger", "message", "traceId", "spanId"):
        assert field in parsed, f"missing archetype field {field}"
    # AC6 level-mapping check.
    assert parsed["level"] == expected_level
    # AC6 logger field — the operator can route the surface by `logger`.
    assert parsed["logger"] == _LOGGER_NAME

    # The three ACME-schema fields ride alongside.
    assert parsed["decision"] == decision.value
    assert parsed["reason"] == reason_value
    # sub is truncated to first-8 + ellipsis because the input is >12 chars.
    assert parsed["sub"] == "session-..."


def test_renderer_emits_null_for_sub_none(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    emit_auth_decision(
        decision=AuthDecision.DENY,
        reason="signature_invalid",
        sub=None,
    )
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    assert len(records) == 1
    rendered = _json_renderer(None, "warning", _event_dict_from_record(records[0]))
    parsed = json.loads(rendered)
    assert parsed["sub"] is None  # JSON null
    assert parsed["decision"] == "deny"
    assert parsed["reason"] == "signature_invalid"


def test_non_auth_decision_record_renders_prior_fixed_shape() -> None:
    """Regression — the renderer must not add decision/sub/reason to other records."""
    record = logging.LogRecord(
        "other.logger", logging.INFO, "x.py", 1, "hello", (), None
    )
    ed = _event_dict_from_record(record)
    parsed = json.loads(_json_renderer(None, "info", ed))
    assert "decision" not in parsed
    assert "sub" not in parsed
    assert "reason" not in parsed


def test_plain_renderer_appends_decision_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
    emit_auth_decision(
        decision=AuthDecision.ALLOW,
        reason="auth_state_created",
        sub=None,
    )
    records = [r for r in caplog.records if r.name == _LOGGER_NAME]
    line = _plain_renderer(None, "info", _event_dict_from_record(records[0]))
    assert "decision=allow" in line
    assert "reason=auth_state_created" in line
    # sub=None must be omitted from the plain-mode wire line.
    assert "sub=" not in line


def _build_production_formatter(renderer: Any) -> structlog.stdlib.ProcessorFormatter:
    """Build the exact foreign_pre_chain + processors list `configure_logging`
    installs in production, so the test exercises the real pipeline end-to-end.
    """
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            _add_timestamp,
            _inject_trace_context,
            _extract_exc_info,
            _lift_auth_decision_fields,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )


def test_production_pipeline_emits_acme_schema_on_the_wire() -> None:
    """End-to-end pipeline test (review-fix P1).

    Drives the helper through the configured `ProcessorFormatter` (same
    foreign_pre_chain + processors as `configure_logging`) and asserts the
    rendered JSON line carries `decision`/`sub`/`reason`. Bypassing the
    processor chain — as the hand-built event_dict tests above could —
    would not catch the regression P1 fixed.
    """
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_build_production_formatter(_json_renderer))
    target = logging.getLogger(_LOGGER_NAME)
    prior_propagate = target.propagate
    target.propagate = False
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    try:
        emit_auth_decision(
            decision=AuthDecision.ALLOW,
            reason="jwt_valid",
            sub="abcdef0123456789",
        )
        handler.flush()
    finally:
        target.removeHandler(handler)
        target.propagate = prior_propagate

    line = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["decision"] == "allow"
    assert parsed["reason"] == "jwt_valid"
    assert parsed["sub"] == "abcdef01..."
    assert parsed["logger"] == _LOGGER_NAME
    assert parsed["level"] == "info"


def test_production_pipeline_omits_decision_fields_for_non_helper_records() -> None:
    """End-to-end: an unrelated `extra={"decision": ...}` record must NOT render
    decision/sub/reason — the sentinel `_is_auth_decision` is what the lift
    gates on, not the raw `decision` attribute (review-fix P5)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(_build_production_formatter(_json_renderer))
    target = logging.getLogger("unrelated.namespace")
    prior_propagate = target.propagate
    target.propagate = False
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    try:
        target.info(
            "audit",
            extra={"decision": "yes", "sub": "alice", "reason": "policy_x"},
        )
        handler.flush()
    finally:
        target.removeHandler(handler)
        target.propagate = prior_propagate

    line = buf.getvalue().strip().splitlines()[-1]
    parsed = json.loads(line)
    assert "decision" not in parsed
    assert "sub" not in parsed
    assert "reason" not in parsed
