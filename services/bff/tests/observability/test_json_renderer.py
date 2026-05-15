import json
from collections.abc import MutableMapping
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from bff.observability.logging import (
    NO_SPAN_ID,
    NO_TRACE_ID,
    _inject_trace_context,
    _json_renderer,
)

_VALID_CTX = SpanContext(
    trace_id=0xABCDEF1234567890ABCDEF1234567890,
    span_id=0x1234567890ABCDEF,
    is_remote=False,
    trace_flags=TraceFlags(TraceFlags.SAMPLED),
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


class TestJsonRenderer:
    def test_json_format_is_valid_json(self) -> None:
        ed = _base_event("json test")
        output = _json_renderer(None, "info", ed)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_json_format_required_fields(self) -> None:
        ed = _base_event("field check")
        parsed = json.loads(_json_renderer(None, "info", ed))
        for field in ("timestamp", "level", "logger", "message", "traceId", "spanId"):
            assert field in parsed

    def test_json_format_camel_case(self) -> None:
        ed = _base_event("case check")
        parsed = json.loads(_json_renderer(None, "info", ed))
        assert "traceId" in parsed
        assert "spanId" in parsed
        assert "trace_id" not in parsed
        assert "span_id" not in parsed

    def test_json_format_utc_iso8601(self) -> None:
        ed = _base_event("ts check", timestamp="2024-06-15T12:00:00+00:00")
        parsed = json.loads(_json_renderer(None, "info", ed))
        assert "+00:00" in parsed["timestamp"]

    def test_json_span_id_populated_with_active_span(self) -> None:
        span = NonRecordingSpan(_VALID_CTX)
        with trace.use_span(span):
            ed = _base_event("span check")
            _inject_trace_context(None, "info", ed)
            parsed = json.loads(_json_renderer(None, "info", ed))
            assert parsed["spanId"] != NO_SPAN_ID
            assert len(parsed["spanId"]) == 16
