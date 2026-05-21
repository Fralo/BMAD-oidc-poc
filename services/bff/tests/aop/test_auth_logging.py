"""Unit tests for `bff.aop.auth_logging` (Story 7.3)."""

from __future__ import annotations

import logging

import pytest

from bff.aop.auth_logging import AuthDecision, _truncate, emit_auth_decision

_LOGGER_NAME = "bff.aop.auth_logging"


class TestLevelMapping:
    """AC1 + AC7 — level mapping table is enforced inside the helper."""

    @pytest.mark.parametrize(
        "decision",
        [
            AuthDecision.ALLOW,
            AuthDecision.LOGIN_SUCCESS,
            AuthDecision.TOKEN_EXCHANGE,
            AuthDecision.REFRESH,
        ],
    )
    def test_info_decisions_emit_at_info(
        self, decision: AuthDecision, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(decision=decision, reason="t", sub=None)
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO
        assert records[0].decision == decision.value  # type: ignore[attr-defined]

    @pytest.mark.parametrize(
        "decision",
        [AuthDecision.DENY, AuthDecision.LOGIN_FAILURE],
    )
    def test_warning_decisions_emit_at_warning(
        self, decision: AuthDecision, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(decision=decision, reason="t", sub=None)
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING


class TestSubTruncation:
    """AC4 — `sub` is truncated to 8 chars + "..." when longer than 12."""

    def test_none_passes_through(self) -> None:
        assert _truncate(None) is None

    def test_empty_string_passes_through(self) -> None:
        assert _truncate("") == ""

    def test_short_sub_passes_through(self) -> None:
        # Under the 12-char threshold — intentional for test-fixture subs.
        assert _truncate("alice") == "alice"

    def test_exactly_twelve_chars_passes_through(self) -> None:
        assert _truncate("abcdefghijkl") == "abcdefghijkl"

    def test_longer_than_twelve_truncates(self) -> None:
        # Real Keycloak `sub` shape: a UUID, ~36 chars. The wire-level
        # ellipsis matches the `_safe_session_id_log` ASCII three-dot
        # convention so two adjacent log lines look the same to operators.
        assert _truncate("0123456789abcdef") == "01234567..."


class TestNameAgnosticTruncation:
    """AC4a — the helper does not look at claim *content*, only length."""

    def test_email_shaped_sub_still_truncates_by_length(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(
            decision=AuthDecision.LOGIN_SUCCESS,
            reason="session_created",
            sub="alice@example.com",
        )
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        # 8-char prefix of "alice@example.com" is "alice@ex"; helper appends "...".
        assert records[0].sub == "alice@ex..."  # type: ignore[attr-defined]


class TestWireFieldShape:
    """AC1 + AC4 + AC6 — wire-field shape on `caplog.records[0]`."""

    def test_emits_all_four_acme_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(
            decision=AuthDecision.ALLOW,
            reason="jwt_valid",
            sub="testuser-uuid-xxxxxxxxxxxxxxxxx",
        )
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        rec = records[0]
        assert rec.name == _LOGGER_NAME  # logger field
        assert rec.decision == "allow"  # type: ignore[attr-defined]
        assert rec.reason == "jwt_valid"  # type: ignore[attr-defined]
        # sub is truncated (length > 12)
        assert rec.sub == "testuser..."  # type: ignore[attr-defined]

    def test_sub_none_passes_through_as_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(
            decision=AuthDecision.LOGIN_FAILURE,
            reason="missing_state",
        )
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        assert records[0].sub is None  # type: ignore[attr-defined]
