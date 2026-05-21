"""Unit tests for `resource_server.aop.auth_logging` (Story 7.3)."""

from __future__ import annotations

import logging

import pytest

from resource_server.aop.auth_logging import (
    AuthDecision,
    _truncate,
    emit_auth_decision,
)

_LOGGER_NAME = "resource_server.aop.auth_logging"


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
        assert _truncate("alice") == "alice"

    def test_exactly_twelve_chars_passes_through(self) -> None:
        assert _truncate("abcdefghijkl") == "abcdefghijkl"

    def test_longer_than_twelve_truncates(self) -> None:
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
        assert rec.name == _LOGGER_NAME
        assert rec.decision == "allow"  # type: ignore[attr-defined]
        assert rec.reason == "jwt_valid"  # type: ignore[attr-defined]
        assert rec.sub == "testuser..."  # type: ignore[attr-defined]

    def test_sub_none_passes_through_as_none(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG, logger=_LOGGER_NAME)
        emit_auth_decision(
            decision=AuthDecision.DENY,
            reason="token_missing",
        )
        records = [r for r in caplog.records if r.name == _LOGGER_NAME]
        assert len(records) == 1
        assert records[0].sub is None  # type: ignore[attr-defined]


class TestClassifyJwtException:
    """Review-fix P3 — pin tests for the PyJWT exception → reason classifier.

    Without these, a future PyJWT release that renames an exception class or
    reorders its MRO could silently shift every emit to the fallback
    `"token_invalid"` and no test in the suite would notice. AC3 names the
    exact mapping; this class pins it.
    """

    def test_invalid_signature_error_maps_to_signature_invalid(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.InvalidSignatureError("bad sig")) == (
            "signature_invalid"
        )

    def test_invalid_audience_error_maps_to_audience_mismatch(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.InvalidAudienceError("bad aud")) == (
            "audience_mismatch"
        )

    def test_invalid_issuer_error_maps_to_issuer_mismatch(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.InvalidIssuerError("bad iss")) == (
            "issuer_mismatch"
        )

    def test_expired_signature_error_maps_to_exp_past(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.ExpiredSignatureError("expired")) == (
            "exp_past"
        )

    def test_missing_required_claim_includes_claim_name(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.MissingRequiredClaimError("sub")) == (
            "claim_missing:sub"
        )

    def test_missing_required_claim_truncates_long_claim_name(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        long_claim = "x" * 32
        result = _classify_jwt_exception(jwt.MissingRequiredClaimError(long_claim))
        assert result == "claim_missing:" + ("x" * 16)

    def test_pyjwk_client_error_maps_to_jwks_lookup_failed(self) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        assert _classify_jwt_exception(jwt.PyJWKClientError("kid not found")) == (
            "jwks_lookup_failed"
        )

    def test_unknown_invalid_token_error_subclass_falls_back_to_token_invalid(
        self,
    ) -> None:
        import jwt

        from resource_server.auth.oidc_bearer import _classify_jwt_exception

        # `DecodeError` is a generic `InvalidTokenError` subclass that we do
        # NOT special-case — it must fall through to the catch-all.
        assert _classify_jwt_exception(jwt.DecodeError("malformed")) == "token_invalid"
