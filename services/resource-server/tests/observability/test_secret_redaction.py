import json
from collections.abc import MutableMapping
from typing import Any

import pytest

from resource_server.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _json_renderer,
    _plain_renderer,
    _redact_secrets,
)


def _base_event(
    message: str = "test message", **extra: Any
) -> MutableMapping[str, Any]:
    ed: MutableMapping[str, Any] = {
        "event": message,
        "level": "info",
        "logger": "test.logger",
        "timestamp": "2024-01-01T00:00:00+00:00",
        "traceId": NO_TRACE_ID,
        "spanId": NO_SPAN_ID,
    }
    ed.update(extra)
    return ed


class TestSecretRedaction:
    @pytest.mark.parametrize(
        "text,expected_redacted",
        [
            ("password=hunter2", "password=***"),
            ("token: abc123xyz", "token: ***"),
            ("api_key=sk-live-12345", "api_key=***"),
            ("apikey=secret", "apikey=***"),
            ("Authorization: Bearer eyJhbGciOi", "Authorization: ***"),
            ("credential=mysecret", "credential=***"),
            ("secret=shh", "secret=***"),
        ],
    )
    def test_redact_known_secret_patterns(
        self, text: str, expected_redacted: str
    ) -> None:
        assert _redact_secrets(text) == expected_redacted

    def test_non_secret_text_unchanged(self) -> None:
        text = "user created id=42 name=Alice"
        assert _redact_secrets(text) == text

    def test_plain_mode_redacts_secrets(self) -> None:
        ed = _base_event("auth password=hunter2 done")
        output = _plain_renderer(None, "info", ed)
        assert "hunter2" not in output
        assert "password=***" in output

    def test_json_mode_redacts_secrets(self) -> None:
        ed = _base_event("got token=abc123")
        parsed = json.loads(_json_renderer(None, "info", ed))
        assert "abc123" not in parsed["message"]
        assert "***" in parsed["message"]
